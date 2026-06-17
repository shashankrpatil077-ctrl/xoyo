#!/usr/bin/env python3
"""
XOYO Deep Research Orchestrator
Implements the 5-phase deep research workflow.
Saves results to SSD for offline access.
"""
import requests, json, time, os

ORCHESTRATOR = "http://localhost:9000/command"
TOKEN = "xoyo-research-2026"
RESEARCH_DIR = os.path.expanduser("~/xoyo/memories/research")
os.makedirs(RESEARCH_DIR, exist_ok=True)


def send_command(prompt: str, timeout: int = 600) -> dict:
    try:
        r = requests.post(ORCHESTRATOR, json={
            "text": prompt,
            "developer_token": TOKEN,
            "source": "autonomous"  # Mark as background service to respect quiet mode
        }, timeout=timeout)
        try:
            return r.json()
        except json.JSONDecodeError:
            return {"response": r.content.decode('utf-8', 'ignore'), "error": "JSON parse failed"}
    except Exception as e:
        return {"error": str(e)}


def run_deep_research(topic: str) -> str:
    """Execute the full 5-phase research workflow."""
    print(f"Starting deep research: {topic}")
    ts = time.strftime("%Y-%m-%d-%H%M%S")
    safe_topic = topic.replace(" ", "_")[:40]
    out_path = f"{RESEARCH_DIR}/{ts}-{safe_topic}.json"

    # Phase 1: Decomposition
    p1 = send_command(
        f"Decompose this research topic into exactly 5 distinct sub-questions "
        f"that together cover all aspects: '{topic}'. Return as numbered list.")

    # Phase 2: Parallel research
    p2 = send_command(
        f"For topic '{topic}', spawn exactly 5 research workers using spawn_workers. "
        f"Sub-questions from previous step: {p1.get('response','')}. "
        f"Each worker must search at least 5 times and return a 300-500 word summary "
        f"with specific facts, dates, statistics, and confidence level.",
        timeout=600)

    time.sleep(90)  # Allow workers to complete

    # Phase 3: Synthesis
    p3 = send_command(
        f"Review all worker research on '{topic}'. Identify contradictions, "
        f"data gaps, and conflicting claims. Launch 3 additional web_search calls "
        f"to resolve the most important discrepancy you found.",
        timeout=300)

    # Phase 4: Deepening
    p4 = send_command(
        f"Based on the research on '{topic}', identify the 3 most fascinating "
        f"threads. Spawn new workers to research each thread at least 2 levels deeper.",
        timeout=300)

    time.sleep(60)

    # Phase 5: Final report
    report = send_command(
        f"Generate the complete deep research report on '{topic}' using all "
        f"gathered information. Include: Executive Summary, Methodology, "
        f"Background, Domain Analysis with confidence levels, Contradictions, "
        f"Key Insights, Limitations, 5 Follow-up Questions, and References. "
        f"Minimum 1500 words. Save as JSON to {out_path}.",
        timeout=300)

    # Save report
    result = {
        "topic": topic,
        "timestamp": ts,
        "phases": {"decomposition": p1, "parallel": p2,
                   "synthesis": p3, "deepening": p4, "report": report},
        "full_report": report.get("response", "")
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    # Write summary to Redis for offline recall (Gap #14)
    try:
        import redis
        rc = redis.Redis(host='localhost', port=6379, decode_responses=True)
        rc.set(f"research:summary:{safe_topic}", json.dumps({
            "topic": topic, "timestamp": ts,
            "summary": report.get("response", "")[:2000],
            "path": out_path,
        }), ex=86400 * 30)  # 30-day TTL
    except Exception:
        pass

    print(f"Research complete. Saved to {out_path}")
    return out_path


if __name__ == "__main__":
    import sys
    topic = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "latest AI breakthroughs 2026"
    run_deep_research(topic)
