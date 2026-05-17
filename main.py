import asyncio
from typing import TypedDict, Annotated, List
from langchain_mcp_adapters.client import MultiServerMCPClient
import os
import sys
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.rate_limiters import InMemoryRateLimiter
import re

import warnings

# Suppress all LangChain schemas / UserWarnings from polluting the console output, gemini is strict about schemas :)
warnings.filterwarnings("ignore", category=UserWarning, module="langchain")
warnings.filterwarnings("ignore", message=".*additionalProperties.*")

load_dotenv()

# Define a rate limiter (e.g., 2 requests per minute for free tier)
rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.033,  # 1 request every 30 seconds
    check_every_n_seconds=0.1,
    max_bucket_size=2,
)

# Attach it to your LLM
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    rate_limiter=rate_limiter
)
memory = InMemorySaver()

#Agent state
class AgentState(TypedDict):
    ticker: str
    research_notes:str
    financial_data:str
    portfolio_status:str
    decision:str #buy/sell/hold decision
    user_approval:bool

#MCP config
brokerage_path = os.path.abspath("brokerage.py")

mcp_config = {
    "brokerage": {
        "command": sys.executable, 
        "args": [brokerage_path],
        "transport": "stdio",
    },
    "researcher_tool": {
        # Using Tavily's production remote server URL
        "command": "npx",
        "args": [
            "-y", 
            "mcp-remote", 
            f"https://mcp.tavily.com/mcp/?tavilyApiKey={os.environ.get('TAVILY_API_KEY')}"
        ],
        "transport": "stdio"
    }
}

async def researcher_node(state: AgentState):
    ticker = state["ticker"]
    print(f"--- RESEARCHER: Investigating {ticker} ---")

    client = MultiServerMCPClient(mcp_config)
    all_tools = await client.get_tools()
    search_tools = [t for t in all_tools if "tavily" in t.name.lower()]
    
    # 1. Ask Gemini to generate the search query/call the tool
    gemini_with_tools = llm.bind_tools(search_tools)
    query = f"Provide a detailed financial summary and recent news for {ticker} stock."
    initial_ai_msg = await gemini_with_tools.ainvoke(query)

    # 2. Extract the actual tool output
    # We manually find the tool and run it to get the raw data for the Advisor
    research_text = ""
    if initial_ai_msg.tool_calls:
        for tool_call in initial_ai_msg.tool_calls:
            # Match the tool name and execute
            tool = next(t for t in search_tools if t.name == tool_call["name"])
            tool_result = await tool.ainvoke(tool_call["args"])
            research_text += str(tool_result)
    else:
        # Fallback if Gemini just answered directly
        research_text = initial_ai_msg.content

    return {"research_notes": research_text}
    
    # finally:
    #     # 4. CRITICAL: Close the client to kill the background MCP processes
    #     await client.close()

async def advisor_node(state: AgentState):
    print(f"--- ADVISOR: Formulating trade strategy ---")
    
    system_msg = (
        "You are a professional algorithmic trading bot. "
        "Analyze the research provided and give a specific verdict. "
        "Your output MUST include the word 'BUY', 'SELL', or 'HOLD', "
        "followed by a quantity (e.g., BUY 10 shares)."
    )
    
    prompt = f"{system_msg}\n\nResearch Data: {state['research_notes']}\n\nTicker: {state['ticker']}"
    response = await llm.ainvoke(prompt)
    return {"decision": response.content}

async def execute_trade_node(state: AgentState):
    print(f"--- EXECUTION: Calling MCP Brokerage ---")
    
    # 1. Gather text state layers
    decision = state.get("decision", "").upper()
    research_notes = state.get("research_notes", "")
    ticker = state["ticker"]
    
    action = "hold"
    quantity = 0
    price = None  

    # 2. Extract action target
    if "BUY" in decision:
        action = "buy"
    elif "SELL" in decision:
        action = "sell"
        
    # 3. Extract quantity using boundaries
    match_qty = re.search(r'\b\d+\b', decision)
    if match_qty:
        quantity = int(match_qty.group())

    # 4. DYNAMIC PRICE EXTRACTION
    # This regex sweeps the Tavily research output looking for numbers tied to currency or market values 
    # Match patterns like: "₹1,336.40", "Rs 1,342", "$150", "at 1364.00"
    price_patterns = [
        r'(?:₹|Rs\.?|INR|\$)\s?(\d{1,4}(?:,\d{3})*(?:\.\d+)?)', # Currency marked symbols
        r'(?:trading at|closed at|price of)\s?(\d{1,4}(?:,\d{3})*(?:\.\d+)?)' # Positional context phrases
    ]
    
    for pattern in price_patterns:
        price_match = re.search(pattern, research_notes, re.IGNORECASE)
        if price_match:
            try:
                cleaned_price = price_match.group(1).replace(",", "")
                price = float(cleaned_price)
                print(f"🎯 DYNAMIC PRICING: Successfully extracted live asset price from research: {price}")
                break
            except ValueError:
                continue

    # Fallback safety buffer if the search text lacked numerical parameters
    if price is None:
        print("⚠️ Warning: Live price not found in research text. Defaulting to a safer estimated baseline.")
        price = 1340.0 # Realistic current market base for RELIANCE.NS

    if action == "hold" or quantity == 0:
        print("--- EXECUTION: Order parameters resulting in HOLD. Transaction aborted. ---")
        return {"portfolio_status": "No action executed (HOLD)"}

    # Visual cost breakdown
    total_transaction_value = price * quantity
    print(f"Ready to execute: {action.upper()} {quantity} shares of {ticker} @ {price} (Total Order Cost: {total_transaction_value})")

    # 5. Connect to your silent Brokerage Engine via MCP Client
    client = MultiServerMCPClient(mcp_config)
    all_tools = await client.get_tools()
    
    trade_tool = next((t for t in all_tools if t.name == "execute_trade"), None)
    if not trade_tool:
        return {"portfolio_status": "Error: execute_trade tool not found on Brokerage server."}

    # 6. Fire live transaction properties to the tool
    tool_result = await trade_tool.ainvoke({
        "ticker": ticker,
        "action": action,
        "quantity": quantity,
        "price": price
    })
    
    status_msg = str(tool_result)
    print(f"Brokerage Core Response: {status_msg}")
        
    return {"portfolio_status": status_msg}
# 4. Building the Graph
workflow = StateGraph(AgentState)

workflow.add_node("researcher", researcher_node)
workflow.add_node("advisor", advisor_node)
workflow.add_node("executor", execute_trade_node)

workflow.set_entry_point("researcher")
workflow.add_edge("researcher", "advisor")

# THE BREAKPOINT: We stop before 'executor' for your approval
workflow.add_edge("advisor", "executor")
workflow.add_edge("executor", END)

# Compile with Interruption
app = workflow.compile(checkpointer=memory, interrupt_before=["executor"])

async def main():
    config = {"configurable": {"thread_id": "1"}}
    initial_input = {"ticker": "NVDA", "approved": False}

    # RUN 1: Starts and pauses before the executor
    async for event in app.astream(initial_input, config):
        for node, values in event.items():
            print(f"Node '{node}' finished.")
            if "decision" in values:
                print(f"ADVISOR RECOMMENDS: {values['decision']}")

    print("\n--- SYSTEM PAUSED: Waiting for your approval ---")
    user_input = input("Type 'yes' to execute this trade: ")

    if user_input.lower() == 'yes':
        # RUN 2: Continue from where we left off
        async for event in app.astream(None, config):
            print(event)

if __name__ == "__main__":
    asyncio.run(main())