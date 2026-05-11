from mcp.server.fastmcp import FastMCP
import os
import json

mcp = FastMCP("Brokerage")
DB_File = 'portfolio.json'

def load_db():
    if not os.path.exists(DB_File):
        return {'balance':10000,"holdings":{}}
    with open(DB_File,"r") as f:
        return json.load(f)
    
@mcp.tool()
def get_portfolio() -> str:
    """Check current cash balance and stock holdings."""

    data = load_db()
    return json.dumps(data, indent = 2)

@mcp.tool()
def execute_trade(ticker:str , action:str, quantity:int, price:float) ->str:
    """Execute a buy or sell trade"""
    data = load_db()
    ticker = ticker.upper()
    cost = price * quantity

    if action.lower() == "buy":
        if data['balance'] < cost:
            return "Error: Insufficient balance."
        data['balance'] -= cost
        data['holdings'][ticker] = data['holdings'].get(ticker,0) + quantity

    elif action.lower() == "sell":
        if data['holdings'].get(ticker,0) < quantity:
            return "Error: You dont own enough {ticker}."
        data['balance'] += cost
        data['holdings'][ticker] -= quantity
        if data['holdings'][ticker] == 0:
            del data['holdings'][ticker]

    with open(DB_File,"w") as f:
        json.dump(data,f)

        return f"Confirmed: {action} {quantity} shares of {ticker} at ${price}."

if __name__ == "__main__":
    mcp.run() 