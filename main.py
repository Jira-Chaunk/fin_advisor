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
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()
#print(f"DEBUG: Tavily Key found: {os.environ.get('TAVILY_API_KEY') is not None}")

llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash")
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
node_dir = r"C:\Program Files\nodejs" # Use 'r' for raw string to handle backslashes
npx_path = os.path.join(node_dir, "npx.cmd")
brokerage_path = os.path.abspath("brokerage.py")


mcp_config = {
    "brokerage": {
        "command": sys.executable, # Points to the current Python with MCP installed
        "args": [os.path.abspath("brokerage.py")],
        "transport": "stdio"
    },
    "researcher_tool": {
        # We call cmd /c and then provide the full path to npx.cmd
        "command": "cmd.exe",
        "args": ["/c", npx_path, "-y", "@tavily/mcp@latest"],
        "transport": "stdio",
        "env": os.environ.copy() 
    }
}

async def researcher_node(state: AgentState):
    ticker = state["ticker"]
    
    print(f"--- RESEARCHER: Investigating {ticker} ---")

    # 1. Initialize the client without 'async with'
    client = MultiServerMCPClient(mcp_config)

        # 2. Get tools directly
    all_tools = await client.get_tools()
        
        # Filter for Tavily (or just use all of them if you prefer)
    search_tools = [t for t in all_tools if "tavily" in t.name.lower()]
        
        # 3. Bind to Gemini
    gemini_with_tools = llm.bind_tools(search_tools)
        
    query = f"Latest financial news and analyst sentiment for {ticker} stock."
    response = await gemini_with_tools.ainvoke(query)
        
    return {"research_notes": response.content}
    
    # finally:
    #     # 4. CRITICAL: Close the client to kill the background MCP processes
    #     await client.close()

async def advisor_node(state: AgentState):
    print(f"--- ADVISOR: Formulating trade strategy ---")
    # Gemini analyzes the notes and decides
    prompt = f"Based on: {state['research_notes']}, what trade should we do for {state['ticker']}? Return action and quantity."
    response = await llm.ainvoke(prompt)
    return {"decision": response.content}

async def execute_trade_node(state: AgentState):
    print(f"--- EXECUTION: Calling MCP Brokerage ---")
    
    # We need to parse the advisor's string decision or have the advisor 
    # return structured data. For now, let's assume simple parsing:
    decision = state["decision"].lower()
    ticker = state["ticker"]
    
    async with MultiServerMCPClient(mcp_config) as client:
        all_tools = await client.get_tools()
        # Find our execute_trade tool
        trade_tool = next(t for t in all_tools if t.name == "execute_trade")
        
        # Note: You'll need to extract quantity/price from the 'decision' text
        # For this example, let's simulate a basic call:
        result = await trade_tool.ainvoke({
            "ticker": ticker,
            "action": "buy" if "buy" in decision else "sell",
            "quantity": 10,
            "price": 150.0  # In a real app, get this from a price tool!
        })
        
    return {"portfolio_status": str(result)}
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