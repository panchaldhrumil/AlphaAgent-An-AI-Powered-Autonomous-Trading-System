# AlgoBot

An AI-powered autonomous trading system implementing the Opening Range Breakout (ORB) strategy with LLM-based agent reasoning and validation.

## Directory Structure

```text
AlgoBot/
├── .env                  ← Place API keys & credentials here
├── auth/
│   └── upstox_auth.py    ← Handles Upstox authentication and token exchange
├── data/
│   └── feed.py           ← Manages WebSocket live market data streams
├── strategy/
│   └── orb.py            ← Contains Opening Range Breakout (ORB) signals logic
├── orders/
│   └── manager.py        ← Place, cancel, and query order execution states
├── agent/
│   └── trader_agent.py   ← LLM decision agent validating strategy signals
├── dashboard/            ← Placeholder for future React dashboard
├── main.py               ← Main entry point integrating the modular flows
└── requirements.txt      ← Required Python packages
```

## Setup & Running

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Configure your API secrets**:
   Open `.env` and fill in your Upstox credentials and Gemini/OpenAI API keys.

3. **Run the integration shell**:
   ```bash
   python main.py
   ```
