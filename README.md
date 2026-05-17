# Financial Advisor Agent (LangGraph & MCP)

This repository implements an autonomous, multi-node trading agent built using **LangGraph**, **LangChain**, and the **Model Context Protocol (MCP)**. The project demonstrates how to orchestrate remote and local tools within a structured state machine while enforcing a strict **Human-in-the-Loop** safety gate before executing transactions.

## Architecture Overview

The system architecture is a deterministic state machine managed by LangGraph, split into three distinct operational layers:

```
[ Researcher Node ] ──> [ Advisor Node ] ──> [ BREAKPOINT ] ──> [ Executor Node ]
  (Remote Tavily)         (LLM Strategy)      (Human Approval)     (Local FastMCP DB)

```

1. **The Researcher (`main.py`)**: Connects to a production remote MCP server (Tavily) using `MultiServerMCPClient` to pull real-time financial news, market summaries, and asset pricing for a given ticker.
2. **The Advisor (`main.py`)**: Uses a Google Gemini LLM (`gemini-2.5-flash`) to process the unstructured research text, reason through market data, and output a specific execution recommendation (e.g., `BUY 10 shares`).
3. **The Executor (`main.py` & `brokerage.py`)**: A localized MCP tool server built with `FastMCP` acting as a mock brokerage. It handles dynamic price parsing via regex from the research text and updates a local portfolio database (`portfolio.json`).

---

## Features

* **Model Context Protocol (MCP)**: Demonstrates tool call standardizations by combining a remote web infrastructure (Tavily search) and a local runtime script (`brokerage.py`) under a unified client interface.
* **Human-in-the-Loop Interruption**: Uses LangGraph's stateful compilation (`interrupt_before=["executor"]`) paired with an `InMemorySaver` checkpointer. The agent halts state execution automatically after the Advisor's step, allowing you to review recommendations before authorizing live state changes.
* **Resilient Parsing**: Incorporates regex pattern-matching engines to extract stock metrics dynamically out of semantic LLM research payloads.
* **Rate Limiting Protection**: Implements an `InMemoryRateLimiter` bound to the Gemini interface to cleanly respect API platform quotas.

---

## File Structure

* `main.py`: Core agent file containing the LangGraph state definition, schema structures, node workflows, and configuration properties.
* `brokerage.py`: A standalone `FastMCP` server initializing the mock brokerage tool dependencies (`get_portfolio`, `execute_trade`) and file persistence logic.
* `run_advisor.py`: Runtime helper wrapper utilizing thread tracking (`thread_id`) to test the system loop interactively via the terminal.
* `portfolio.json`: The local data layer managing mock cash balances and stock holding quantities.

---

## Prerequisites

Ensure you have Python 3.10+ installed along with Node.js/npx (required for the remote MCP client layer).

Install the necessary dependencies:

```bash
pip install langchain-mcp-adapters langgraph langchain-google-genai fastmcp python-dotenv

```

Set up your environment configurations in a `.env` file at the project root:

```env
GOOGLE_API_KEY=your_gemini_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here

```

---

## Getting Started

To execute the interactive trading flow simulation:

```bash
python run_advisor.py

```

### Flow Lifecycle:

1. The script initializes the state graph and begins searching for the target asset.
2. The Advisor outputs its strategy assessment directly to the console.
3. The graph state **pauses automatically** and outputs `--- SYSTEM INTERRUPTED ---`.
4. Enter `yes` in your terminal to safely resume execution and invoke the mock brokerage backend, or enter any other value to cancel the transaction.

---

## Disclaimer

This repository was built strictly for technical exploration, educational research, and architectural learning regarding Agentic AI orchestration, LangChain, and MCP. It is **not financial software**, nor does it provide valid trading guidance. Do not use this engine with actual capital or financial platforms.
