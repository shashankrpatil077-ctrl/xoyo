import os
import sys
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Add parent directory to sys.path to import orchestrator
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.llm_router import call_llm

app = FastAPI(title="XOYO AI Scientist Framework")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ResearchRequest(BaseModel):
    task: str
    iterations: int = 1

class ResearchResponse(BaseModel):
    task: str
    paper: str

def run_agent(persona: str, system_prompt: str, user_prompt: str) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    logger.info(f"Running persona: {persona}")
    response = call_llm(messages, max_tokens=2000, temperature=0.7, task_type="science")
    return response

@app.post("/research", response_model=ResearchResponse)
def research(req: ResearchRequest):
    logger.info(f"Starting research task: {req.task}")
    
    current_knowledge = ""
    
    for i in range(req.iterations):
        logger.info(f"--- Iteration {i+1} ---")
        
        # 1. Researcher
        researcher_sys = "You are the Lead Researcher. Formulate hypotheses and gather initial insights based on the given task and previous knowledge."
        researcher_prompt = f"Task: {req.task}\nPrevious Knowledge: {current_knowledge}\nProvide your research insights."
        researcher_out = run_agent("Researcher", researcher_sys, researcher_prompt)
        
        # 2. Analyst
        analyst_sys = "You are the Data Analyst. Analyze the researcher's insights, simulate or design data experiments to support or refute the hypothesis."
        analyst_prompt = f"Task: {req.task}\nResearcher Insights:\n{researcher_out}\nProvide your data analysis and methodology."
        analyst_out = run_agent("Analyst", analyst_sys, analyst_prompt)
        
        # 3. Reviewer
        reviewer_sys = "You are the Peer Reviewer. Critique the researcher's hypothesis and the analyst's methodology for logical fallacies or errors."
        reviewer_prompt = f"Task: {req.task}\nResearcher:\n{researcher_out}\nAnalyst:\n{analyst_out}\nProvide your peer review."
        reviewer_out = run_agent("Reviewer", reviewer_sys, reviewer_prompt)
        
        # Synthesizer
        synth_sys = "You are the Lead Scientist synthesizing a research paper section from the team's work."
        synth_prompt = f"Synthesize this into a cohesive section of a research paper.\nResearcher: {researcher_out}\nAnalyst: {analyst_out}\nReviewer: {reviewer_out}"
        synthesis = run_agent("Synthesizer", synth_sys, synth_prompt)
        
        current_knowledge += f"\n\nIteration {i+1} Synthesis:\n{synthesis}"
        
    # Final Paper Generation
    final_sys = "You are the Lead Scientist. Write a final, formatted research paper based on the syntheses."
    final_prompt = f"Task: {req.task}\nSyntheses: {current_knowledge}\nWrite the final research paper in Markdown format."
    final_paper = run_agent("Finalizer", final_sys, final_prompt)
    
    logger.info("Research completed.")
    return ResearchResponse(task=req.task, paper=final_paper)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8060)
