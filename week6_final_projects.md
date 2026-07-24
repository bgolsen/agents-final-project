# Capstone Project: Rubric & Guidelines

## AI Agents — Graduate Course

---

## Overview

The capstone project is your opportunity to synthesize the concepts, frameworks, and engineering practices from Weeks 1–5 into a cohesive, working agentic system. You will select one of the five approved project tracks (or propose your own, subject to instructor approval), design a multi-agent architecture, implement it using at least two frameworks covered in the course, and submit a recorded presentation with a live demo of your system.

---

## Approved Project Tracks

### Track 1: Autonomous Research & Literature Review Assistant

Build a system that takes a research question, decomposes it into sub-queries, searches and retrieves papers (via Semantic Scholar or arXiv APIs), synthesizes findings, identifies contradictions across sources, and produces a structured literature review draft. HITL checkpoints allow a human reviewer to approve or redirect the research direction at key branching points.

**Technical emphasis:** Planning and task decomposition (Week 3), multi-agent specialization (a retrieval agent, a synthesis agent, a contradiction-detection agent), LangGraph for the approval workflow (Week 5). LangSmith evaluation tracks retrieval relevance and synthesis quality.

### Track 2: Multi-Agent Incident Response System

Given a simulated production incident (service degradation, security alert, etc.), multiple agents collaborate to triage, diagnose root cause, propose remediation, and draft a post-mortem. One agent monitors logs/metrics (simulated data), another queries a knowledge base of past incidents, a third proposes and ranks remediation steps using hierarchical planning, and a coordinator manages handoffs. HITL gates the actual remediation execution.

**Technical emphasis:** A2A-style coordination (Week 4), n8n for alerting/routing workflows (Week 3), LangSmith for tracing the diagnostic reasoning chain (Week 5). Requires designing agent communication protocols and handling partial information.

### Track 3: Personalized Learning Path Generator

Given a learner's background, target skill, and time budget, the system builds a customized curriculum by searching course catalogs and open educational resources, sequencing content with prerequisite reasoning, generating practice exercises, and adapting the plan based on simulated assessment results. HITL checkpoints allow the learner to provide feedback that triggers replanning.

**Technical emphasis:** Classical planning concepts — goal decomposition, constraint satisfaction, prerequisite ordering (Week 3). Multi-agent roles (curriculum designer agent, assessment agent, resource discovery agent). Strong evaluation story — plan coherence, prerequisite ordering accuracy, and adaptation quality are all measurable.

### Track 4: Collaborative Investment Research Platform

Agents specialize in different analysis dimensions: financial data retrieval and ratio analysis, news sentiment processing, sector/macro trend evaluation. An orchestrator synthesizes a recommendation with explicit reasoning chains. The HITL checkpoint is an investment committee approval step before any recommendation is finalized.

**Technical emphasis:** Tool use and API integration (Week 2 — financial data APIs, news APIs), planning (building and updating an investment thesis as new data arrives), A2A coordination between specialist agents (Week 4). LangSmith evaluation tracks reasoning quality and recommendation consistency.

### Track 5: Code Review & Refactoring Pipeline

Build a multi-agent system that takes a codebase (or PR diff), performs automated review across dimensions (security vulnerabilities, performance, style, test coverage gaps), proposes refactoring plans with dependency-aware ordering, and generates the refactored code for human review. The planning layer determines refactoring order to avoid breaking changes. HITL approves each refactoring step before execution.

**Technical emphasis:** Dependency-aware planning and ordering (Week 3), multi-dimensional parallel analysis with synthesis, HITL approval workflows (Week 5). Concrete evaluation story — performance can be measured against known code smells in a test corpus.

---

Students may propose an alternative project of comparable scope. Proposals must be submitted in writing and approved by the instructor no later than the end of Week 4\.

---

## Requirements

### Framework Integration (Mandatory)

Your project must incorporate **at least two** of the following frameworks/platforms covered in the course:

- CrewAI (Week 1\)  
- Google ADK (Week 2\)  
- n8n (Week 3\)  
- A2A Protocol (Week 4\)  
- LangGraph with HITL (Week 5\)

You must justify your framework selections in your architecture document — explain why each framework was chosen for its role and what tradeoffs you considered.

### Minimum Technical Scope

Every capstone project, regardless of track, must demonstrate all of the following:

1. **Multi-agent architecture** — At least three distinct agents with clearly defined roles, goals, and responsibilities  
2. **Planning or reasoning** — Explicit task decomposition, goal hierarchies, or multi-step reasoning (not just sequential tool calls)  
3. **Tool use or external integration** — At least two external APIs, data sources, or tool integrations  
4. **Human-in-the-Loop** — At least one meaningful HITL checkpoint where a human reviews, approves, or redirects agent behavior  
5. **Observability** — Logging, tracing, or LangSmith integration that makes the system's decision-making inspectable  
6. **Error handling** — Graceful degradation when tools fail, APIs are unavailable, or agents produce unexpected outputs

---

## Deliverables

| Deliverable | Format | Description |
| :---- | :---- | :---- |
| **Working system** | GitHub repository | Complete, runnable code with a README containing setup instructions. The system must be demonstrable. |
| **Architecture document** | Markdown or PDF (2–4 pages) | System design, agent roles, framework justification, data flow, and key design decisions. Include at least one architecture diagram. |
| **Technical analysis** | Section within architecture doc (1–2 pages) | Critical reflection connecting your implementation to course concepts — which planning paradigm did you use and why? How does your coordination model compare to alternatives? What are the limitations? |
| **Presentation & demo video** | Video recording (10 minutes max) | A single recording that combines your project presentation with a live demo. Cover your architecture, design rationale, and tradeoffs, then demonstrate the system in action — showing agent interactions, HITL checkpoints, and handling of at least one failure/edge case. |

---

## Grading Rubric

**Total: 500 points**

### 1\. Architecture & Design (125 points)

- **Agent design (45):** Agents have clearly distinct roles with well-defined boundaries. Role assignment is justified and avoids redundancy.  
- **Framework selection (40):** Frameworks are well-chosen for their respective tasks with thoughtful justification of tradeoffs in the architecture document.  
- **System coherence (40):** Components fit together into a unified architecture with clear data flow and well-defined interfaces. Includes at least one architecture diagram.

### 2\. Planning & Reasoning (100 points)

- **Task decomposition (35):** Complex tasks are broken into well-structured subtask hierarchies. Decomposition strategy is explicit and inspectable — not hard-coded.  
- **Reasoning quality (35):** Agents demonstrate multi-step reasoning with explicit chain-of-thought, traceable in logs or traces.  
- **Adaptability (30):** System handles disruptions, unexpected inputs, or partial failures by replanning or adjusting strategy rather than crashing.

### 3\. Implementation Quality (100 points)

- **Code quality (25):** Clean, well-organized code with consistent structure, meaningful naming, appropriate comments, and documented dependencies.  
- **Error handling (25):** Graceful degradation when tools fail, APIs are unavailable, or agents produce unexpected outputs. Meaningful error messages and recovery strategies.  
- **HITL implementation (25):** HITL checkpoints are meaningful decision points where human input genuinely affects system behavior — not rubber-stamp confirmations.  
- **Observability (25):** Structured traces or logs that make agent decision-making transparent. LangSmith or equivalent integration.

### 4\. Technical Analysis & Reflection (75 points)

- **Conceptual grounding (30):** Implementation decisions are explicitly connected to course concepts (planning paradigms, coordination models, tool-use patterns).  
- **Tradeoff analysis (25):** Discusses what was gained and lost by architectural choices. Considers alternatives that were rejected and explains why.  
- **Limitations & future work (20):** Honestly identifies system limitations and failure modes. Proposes concrete next steps.

### 5\. Presentation & Demo Recording (100 points)

- **Presentation clarity (40):** Clear, well-structured recording that communicates architecture and design rationale effectively within the 10-minute limit.  
- **Demo quality (40):** System is demonstrated end-to-end showing agent interactions, HITL checkpoints, and handling of at least one failure/edge case. Running code, not just slides.  
- **Production quality (20):** Audio is clear, screen content is legible, pacing is appropriate.

---

## Grading Summary

| Category | Points |
| :---- | :---- |
| Architecture & Design | 125 |
| Planning & Reasoning | 100 |
| Implementation Quality | 100 |
| Technical Analysis & Reflection | 75 |
| Presentation & Demo Recording | 100 |
| **Total** | **500** |

---

## Bonus Opportunities (Up to 100 additional points)

- **Open-source contribution (+40):** Publishes a reusable component, tool, or template derived from the project as a public package or repository. Must include proper documentation (README with usage examples, API reference), a permissive license (MIT, Apache 2.0, etc.), and be installable or importable by others. Simply making the project repo public does not qualify — the contribution must be a self-contained, general-purpose artifact that others could use outside the context of this course.  
- **Containerization (+25):** System is fully containerized with Docker Compose and can be launched with a single command. Includes health checks, environment variable configuration, and a documented setup process that works on a fresh machine.  
- **Automated evaluation (+20):** Includes a test suite or evaluation pipeline that measures agent performance against defined metrics (e.g., task completion rate, reasoning accuracy, latency). Must run reproducibly and produce a summary report.  
- **Novel integration (+15):** Incorporates a framework, protocol, or technique not covered in the course (e.g., LangChain, AutoGen, DSPy) with written justification for its inclusion and analysis of what it added to the system.

Bonus points cannot exceed 100 and cannot raise the total beyond 600\.

---

## Submission Guidelines

- **Repository:** Submit a GitHub repository link via Canvas. The repository must be accessible to the instructor (public or with collaborator access granted).  
- **Due date:** End of Week 5 (exact date on Canvas). Late submissions lose 50 points per day.  
- **Architecture document:** Include in the repository root as `ARCHITECTURE.md`.  
- **Presentation & demo video:** Upload to Canvas or link to an unlisted YouTube/Loom video in the README. Maximum 10 minutes.

---

## Academic Integrity

- All code must be your own original work. You may use libraries, frameworks, and APIs, but the agent logic, architecture, and integration must be yours.  
- Use of AI coding assistants (GitHub Copilot, Claude, ChatGPT, etc.) is permitted for implementation assistance, but you must be able to explain every line of your code. The instructor may request a follow-up conversation to verify understanding.  
- If you adapt code from tutorials, documentation, or open-source projects, cite the source in your code comments and README.  
- Plagiarism of architecture documents or analysis from other students or external sources will result in a zero for the entire capstone.

