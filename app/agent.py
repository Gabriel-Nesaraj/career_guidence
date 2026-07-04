import os
import re
import json
import sys
from datetime import datetime
from typing import List, Optional, Any, AsyncGenerator

from google.adk.workflow import Workflow, node, START, JoinNode
from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.apps import App, ResumabilityConfig
from google.adk.models import Gemini
from google.genai import types
from pydantic import BaseModel, Field

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from app.config import config

# --- Pydantic Schemas ---

class SyllabusMilestone(BaseModel):
    title: str = Field(description="Title of the milestone/unit")
    description: str = Field(description="Short description of what is covered")
    estimated_hours: int = Field(description="Estimated hours to complete this milestone")
    suggested_resources: List[str] = Field(description="Suggested free learning resources or articles")

class StudyPlan(BaseModel):
    subject: str = Field(description="The subject of study")
    target_audience: str = Field(description="Who this study plan is tailored for")
    total_weeks: int = Field(description="Total weeks estimated")
    milestones: List[SyllabusMilestone] = Field(description="List of learning milestones")

class QuizQuestion(BaseModel):
    question: str = Field(description="The question text")
    options: List[str] = Field(description="Multiple choice options")
    correct_option_index: int = Field(description="0-based index of the correct option")
    explanation: str = Field(description="Explanation of the correct answer")

class PracticeQuiz(BaseModel):
    subject: str = Field(description="Subject of the quiz")
    questions: List[QuizQuestion] = Field(description="List of quiz questions")

class OrchestratorResponse(BaseModel):
    intent: str = Field(description="The detected user intent: 'syllabus', 'quiz', or 'general'")
    message: str = Field(description="A message explaining what is happening or answering the user")
    study_plan: Optional[StudyPlan] = Field(default=None, description="The study plan if created/updated")
    quiz: Optional[PracticeQuiz] = Field(default=None, description="The quiz if created/updated")


# --- MCP Toolset Integration ---
python_exe = sys.executable or "python3"
current_dir = os.path.dirname(os.path.abspath(__file__))
mcp_server_path = os.path.join(current_dir, "mcp_server.py")

mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=python_exe,
            args=[mcp_server_path],
        )
    )
)

# --- Sub-Agents ---
model = Gemini(model=config.model)

syllabus_planner = LlmAgent(
    name="syllabus_planner",
    model=model,
    instruction="""You are a Syllabus Planner. Your goal is to design highly customized, structured study plans for students.
Always try to use the search_educational_resources tool to find and suggest free and accessible resources for the milestones.
Always try to use the calculate_study_pace tool to estimate the total duration based on the student's study availability.
Format your output strictly according to the StudyPlan schema.
""",
    output_schema=StudyPlan,
    tools=[mcp_toolset]
)

quiz_generator = LlmAgent(
    name="quiz_generator",
    model=model,
    instruction="""You are a Quiz Generator. Your goal is to create practice quizzes with multiple-choice questions to test the student's understanding of the subject.
Format your output strictly according to the PracticeQuiz schema.
""",
    output_schema=PracticeQuiz,
    tools=[mcp_toolset]
)

# --- Orchestrator ---
orchestrator = LlmAgent(
    name="orchestrator",
    model=model,
    instruction="""You are the Curriculum Orchestrator.
Your goal is to guide students on their learning path.
You have access to two specialized sub-agents:
1. syllabus_planner: for creating custom study plan structures and milestones.
2. quiz_generator: for generating practice quizzes.

Use the AgentTools to delegate tasks:
- If the user asks for a new curriculum, study path, syllabus, or asks to revise an existing plan, delegate to syllabus_planner.
- If the user wants to be tested, take a quiz, or test their knowledge on a topic, delegate to quiz_generator.

In your final response:
- Set 'intent' to 'syllabus' if you created or revised a syllabus.
- Set 'intent' to 'quiz' if you generated a quiz.
- Set 'intent' to 'general' for general conversation or feedback.
- Provide a friendly explanation in 'message'.
""",
    output_schema=OrchestratorResponse,
    tools=[AgentTool(syllabus_planner), AgentTool(quiz_generator)]
)


# --- Workflow Graph Nodes ---

def extract_text(node_input: Any) -> str:
    if hasattr(node_input, 'parts') and node_input.parts:
        return "".join([part.text for part in node_input.parts if hasattr(part, 'text') and part.text])
    elif isinstance(node_input, str):
        return node_input
    elif isinstance(node_input, dict):
        return json.dumps(node_input)
    return str(node_input)

def security_checkpoint(ctx: Context, node_input: Any) -> Event:
    text = extract_text(node_input)
    
    # 1. PII Redaction
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    phone_pattern = r'\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}'
    
    scrubbed_text = text
    email_matches = re.findall(email_pattern, text)
    phone_matches = re.findall(phone_pattern, text)
    
    if email_matches or phone_matches:
        scrubbed_text = re.sub(email_pattern, "[REDACTED_EMAIL]", scrubbed_text)
        scrubbed_text = re.sub(phone_pattern, "[REDACTED_PHONE]", scrubbed_text)
        audit_log = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": "pii_redaction",
            "severity": "INFO",
            "details": f"Redacted {len(email_matches)} emails and {len(phone_matches)} phone numbers"
        }
        print(json.dumps(audit_log))
        
    # 2. Prompt Injection Detection
    injection_keywords = [
        "ignore previous instructions", 
        "system prompt", 
        "override instructions", 
        "dan mode", 
        "jailbreak",
        "you are now",
        "translate the above"
    ]
    has_injection = any(kw in text.lower() for kw in injection_keywords)
    if has_injection:
        audit_log = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": "prompt_injection_detected",
            "severity": "CRITICAL",
            "details": f"Input triggered prompt injection filter. Raw input: {text}"
        }
        print(json.dumps(audit_log))
        return Event(output="Security Check Failed: Prompt Injection Attempt Blocked.", route="security_event")
        
    # 3. Domain Specific Filter (Appropriate Educational Content)
    inappropriate_keywords = ["bomb", "weapon", "drugs", "hacking", "cheating", "crack", "steal", "robbery"]
    has_inappropriate = any(re.search(rf"\b{kw}\b", text.lower()) for kw in inappropriate_keywords)
    if has_inappropriate:
        audit_log = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": "inappropriate_content_detected",
            "severity": "WARNING",
            "details": f"User requested inappropriate educational topic. Raw input: {text}"
        }
        print(json.dumps(audit_log))
        return Event(output="Security Check Failed: Topic must be appropriate for academic education.", route="security_event")
        
    # All checks passed
    audit_log = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": "security_check_passed",
        "severity": "INFO",
        "details": "Input cleared by security checkpoint"
    }
    print(json.dumps(audit_log))
    return Event(output=scrubbed_text, route="cleared", state={"clean_input": scrubbed_text})

def security_event(node_input: str) -> Event:
    content = types.Content(
        role="model",
        parts=[types.Part.from_text(text=f"⚠️ [Security Event] {node_input}")]
    )
    yield Event(content=content)
    yield Event(output=node_input)

def route_orchestrator_output(ctx: Context, node_input: dict) -> Event:
    intent = node_input.get("intent", "general")
    message = node_input.get("message", "")
    
    state_updates = {"last_intent": intent, "orchestrator_message": message}
    
    if node_input.get("study_plan"):
        state_updates["temp_study_plan"] = node_input["study_plan"]
        
    if node_input.get("quiz"):
        state_updates["temp_quiz"] = node_input["quiz"]
        
    if intent == "syllabus" and not ctx.state.get("approved"):
        return Event(output=message, route="needs_approval", state=state_updates)
    
    return Event(output=message, route="done", state=state_updates)

async def ask_student_approval(ctx: Context, node_input: str) -> Event:
    study_plan = ctx.state.get("temp_study_plan")
    syllabus_text = ""
    if study_plan:
        syllabus_text += f"\n\n### Proposed Study Plan: {study_plan.get('subject')}\n"
        syllabus_text += f"Tailored for: {study_plan.get('target_audience')} | Total duration: {study_plan.get('total_weeks')} weeks\n\n"
        for i, m in enumerate(study_plan.get("milestones", [])):
            syllabus_text += f"**Milestone {i+1}: {m.get('title')}** ({m.get('estimated_hours')} hours)\n"
            syllabus_text += f"- Description: {m.get('description')}\n"
            syllabus_text += "- Resources:\n"
            for res in m.get("suggested_resources", []):
                syllabus_text += f"  * {res}\n"
            syllabus_text += "\n"
            
    prompt_message = f"{node_input}{syllabus_text}\n\n✋ Do you approve this custom study plan? (yes/no/changes)"
    
    yield Event(content=types.Content(role="model", parts=[types.Part.from_text(text=prompt_message)]))
    yield RequestInput(interrupt_id="student_approval", message="Syllabus Approval Check")

def process_student_approval(ctx: Context, node_input: str) -> Event:
    feedback = node_input.strip()
    if feedback.lower() in ["yes", "approve", "approved", "y"]:
        study_plan = ctx.state.get("temp_study_plan")
        return Event(
            output="Congratulations! Your custom study plan has been approved and saved. Let me know if you want to take a practice quiz or revise anything!",
            route="approved",
            state={"study_plan": study_plan, "approved": True}
        )
    else:
        return Event(
            output=f"Student requested changes to the study plan: {feedback}",
            route="revise",
            state={"approved": False, "student_feedback": feedback}
        )

def final_output(node_input: Any) -> Event:
    text = str(node_input)
    content = types.Content(
        role="model",
        parts=[types.Part.from_text(text=text)]
    )
    yield Event(content=content)
    yield Event(output=text)


# --- Workflow Graph Definition ---

root_agent = Workflow(
    name="root_agent",
    edges=[
        ("START", security_checkpoint),
        (security_checkpoint, {"security_event": security_event, "cleared": orchestrator}),
        (orchestrator, route_orchestrator_output),
        (route_orchestrator_output, {"needs_approval": ask_student_approval, "done": final_output}),
        (ask_student_approval, process_student_approval),
        (process_student_approval, {"approved": final_output, "revise": orchestrator}),
    ]
)

app = App(
    name="app",
    root_agent=root_agent,
    resumability_config=ResumabilityConfig(is_resumable=True)
)
