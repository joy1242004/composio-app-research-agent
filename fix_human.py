import json
from pathlib import Path

DATA = Path("data")

with open(DATA / "apps_final.json", encoding="utf-8") as f:
    apps = json.load(f)

for app in apps:
    if app["name"] == "Otter AI":
        app["source"] = "human-spot-checked"
        app["verified"] = True

        app["auth"] = "OAuth-based MCP"
        app["mcp"] = "Official MCP server"
        app["surface"] = "No broad public REST API; official MCP integration"
        app["verdict"] = "Buildable"
        app["blocker"] = "No broad public REST API; integration surface is MCP-based"

        app["evidence"] = (
            "https://help.otter.ai; "
            "https://mcp.otter.ai/mcp"
        )

        app["evidenceSnippet"] = (
            "Human spot-check found no broad public REST API for third parties; "
            "the documented integration surface is an official OAuth-based MCP server."
        )

        app["confidence"] = "High"

        print("Updated Otter AI as human-spot-checked.")
        break
else:
    raise SystemExit("Otter AI not found.")

with open(DATA / "apps_final.json", "w", encoding="utf-8") as f:
    json.dump(apps, f, indent=2, ensure_ascii=False)

print("Saved data/apps_final.json")