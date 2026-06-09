# AI Jumpstart MVP using GB10 - Iteration 1 Prompt

**System / Primary Instruction:**
Act as a Senior AI Solutions Architect and Supply Chain Optimization (SCO) Strategist. I am an AI Intern at Helix, Connection Inc., and my manager, Ryan, has assigned me to a high-impact project: building an "AI Jumpstart MVP using GB10." I have uploaded five whiteboard photos (`Pic 1.jpeg` through `Pic 5.jpeg`) and a research paper (`12806_Robustness_of_Policy_Gra.pdf`) outlining the project architecture, goals, and phases. 

Below is the full context for the attached files. Please digest this entire project scope to inform your understanding, but **only execute the specific Iteration 1 task requested at the bottom of this prompt.**

## The Full Project Context:

* **Pic 1 (Domain & Target Industries):** The core idea is to completely "AI-fy" the supply chain mechanism. The left side breaks down the Supply Chain skeleton: demand, capacity, routing & logistics, and costs. The right side lists our target industries for application: Manufacturing, Retail, Wholesale & Logistics, and Hospitals. 
* **Pic 2 (Hardware & Architecture):** Our final application will reside entirely within 1x or 2x nodes of the NVIDIA GB10 (Grace Blackwell Superchip). The GB10 is a compact AI supercomputer featuring a 20-core ARM CPU, Blackwell GPU, 128GB of unified memory, and up to 1 PetaFLOP of FP4 compute. We will utilize its raw hardware power, local LLM capabilities, and the CUDA/cuOpt libraries to run the whole stack. 
* **Pic 3 (High-Level Product Flow):** Helix will sell this finalized "AI Jumpstart Service" packaged inside the GB10 hardware directly to customers. Customers plug their raw data into this device, and our AI app locally handles their entire supply chain optimization securely.
* **Pic 4 (Project Iterations & Requirements):** Ryan has outlined four main phases:
    1.  *Use cases:* Identify the problems/challenges, outcomes/benefits, and the % of improvement.
    2.  *Identify data elements -> data pipeline.*
    3.  *Research & recommend "SCO" scaffolding.*
    4.  *Build a Synthetic Data Set.*
* **Pic 5 & `12806_Robustness_of_Policy_Gra.pdf` (Technical Stack & Empirical Modeling):** The underlying engine running on the GB10 must include a Vector Database, an LLM + RAG architecture, and Empirical AI Modeling. **Crucially**, the Empirical AI Modeling strategy must be backed by the findings in my attached research paper on robust Policy-Gradient RL for Multi-Echelon Inventory Control.

---

## Your Task for Iteration 1:
Ryan only wants to see deliverables for **Pic 4, Points 1 and 2** for now. Generate a highly professional, presentation-ready draft addressing the following:

### 1. Use Cases & Value Proposition:
Create a detailed breakdown for each of the 4 target industries (Manufacturing, Retail, Wholesale & Logistics, Hospitals). For each industry, across our supply chain pillars, identify:
* **Problems & Challenges:** Detail their current operational pain points. Frame their current legacy methods (like classic Operations Research heuristics or simple reorder-point policies) as the "villains" that collapse under non-stationary shocks, referencing the concepts in my paper. 
* **Outcomes & Benefits:** How does our GB10-powered solution specifically solve them?
* **% Improvement:** Provide realistic estimated improvement percentages that we can use to pitch the ROI. **You must use the performance gaps cited in my research paper (e.g., the 36% to 94% improvements of continuous-action PPO over fixed analytical baselines during distribution shifts) to justify these estimates.**

### 2. Identify Data Elements & Data Pipeline (Integrating Pic 5 & The Research Paper):
* **Data Elements:** List the specific types of raw data we need to ingest from these clients to feed the engine.
* **Conceptual Data Pipeline:** Map out the high-level data pipeline architecture. Describe how customer data flows from its raw state and interacts with the tech stack:
    * How the data is embedded into the **Vector DB**.
    * How the **LLM + RAG** setup queries this data.
    * **Empirical AI Modeling Integration:** At a high level, explain how we will deploy PPO algorithms on the GB10 to handle multi-echelon inventory routing and adapt to complex, non-stationary environments. *(Constraint: Keep this architectural for now. Do not write out the specific mathematical cost functions, reward signals, or state-space matrices from the paper. We will tackle the granular math in later iterations).*

*Constraint: Do not address the SCO scaffolding (Point 3) or the Synthetic Dataset generation (Point 4) yet. Format your response with clean headers, bullet points, and tables to make it highly scannable.*