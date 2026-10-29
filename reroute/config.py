"""Settings read from environment variables (or a .env file in the project root)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

try:  # python-dotenv is optional
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# "sqlite" (default, no setup) or "hana" (SAP HANA Cloud)
DB_BACKEND = os.getenv("REROUTE_DB", "sqlite").lower()
SQLITE_PATH = os.getenv("REROUTE_SQLITE_PATH", str(ROOT / "reroute.db"))

HANA = {
    "address": os.getenv("HANA_HOST", ""),
    "port": int(os.getenv("HANA_PORT", "443")),
    "user": os.getenv("HANA_USER", ""),
    "password": os.getenv("HANA_PASSWORD", ""),
    "schema": os.getenv("HANA_SCHEMA", ""),
}

# Generative AI Hub (SAP AI Core). The SDK reads the AICORE_* variables itself.
AICORE_VARS = ["AICORE_CLIENT_ID", "AICORE_CLIENT_SECRET", "AICORE_AUTH_URL", "AICORE_BASE_URL", "AICORE_RESOURCE_GROUP"]
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
# Deployment URL of the orchestration deployment (AI Launchpad > ML Operations > Deployments >
# defaultOrchestrationConfig > Deployment URL). When set, every model in the hub works, e.g. Claude.
ORCHESTRATION_URL = os.getenv("ORCHESTRATION_URL", "").rstrip("/")
LLM_DISABLED = os.getenv("REROUTE_LLM", "on").lower() == "off"

# SAP Business Accelerator Hub sandbox (api.sap.com)
S4_SANDBOX_API_KEY = os.getenv("S4_SANDBOX_API_KEY", "")
# Full URL of the purchase order list from the API's Try Out page (needed for the newer OData V4 API)
S4_SANDBOX_PO_URL = os.getenv("S4_SANDBOX_PO_URL", "").rstrip("/")
S4_SANDBOX_BASE = os.getenv(
    "S4_SANDBOX_BASE",
    "https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV",
)

# Autonomy limits for the Policy agent: inside these, agents act alone; outside, a human approves
AUTO_COST_LIMIT_INR = float(os.getenv("AUTO_COST_LIMIT_INR", "100000"))      # extra cost vs doing nothing
BIG_SWITCH_LIMIT_INR = float(os.getenv("BIG_SWITCH_LIMIT_INR", "5000000"))   # order value moved to another supplier

# How the ranking weighs the three goals in the "Balanced" plan (must add to 1)
WEIGHTS_BALANCED = {"cost": 0.25, "delay": 0.40, "service": 0.35}
