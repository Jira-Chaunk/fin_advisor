import asyncio
from main import app  # Import the 'app' we defined in the previous step

async def run_loop():
    # 1. Thread ID allows LangGraph to remember the state for this specific user
    config = {"configurable": {"thread_id": "test_run_001"}}
    
    # 2. Start the process
    # We pass the initial ticker we want to analyze
    initial_input = {"ticker": "RELIANCE.NS"} 
    
    print("--- STARTING AGENTIC FLOW ---")
    async for event in app.astream(initial_input, config, stream_mode="values"):
        # This will print the state as it updates
        ticker = event.get("ticker")
        decision = event.get("decision")
        if decision:
            print(f"\n[ADVISOR RECOMMENDATION]:\n{decision}\n")

    # 3. The Pause (Human in the Loop)
    # At this point, the graph has hit the 'executor' breakpoint
    print("--- SYSTEM INTERRUPTED ---")
    print("The Advisor has made a suggestion. Check your state or 'portfolio.json'.")
    
    confirm = input("Should I execute this trade? (yes/no): ")

    if confirm.lower() == "yes":
        print("--- RESUMING FLOW ---")
        # To resume, we pass 'None' as the input but keep the same 'config' (thread_id)
        async for event in app.astream(None, config, stream_mode="values"):
            if "portfolio_status" in event:
                print(f"RESULT: {event['portfolio_status']}")
    else:
        print("Trade cancelled by user.")

if __name__ == "__main__":
    asyncio.run(run_loop())