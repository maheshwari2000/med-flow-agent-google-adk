"""
MedFlow with Conflict Resolution
Architecture: Triage All → Resolve Conflicts → Allocate Resources → Summarize
"""

from google.adk.agents import LlmAgent, SequentialAgent
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Union, Literal
from med_agent.customTools import *

# ============================================================================
# LLM SCHEMAS
# ============================================================================

class TriageDecision(BaseModel):
    """Single patient triage assessment"""
    patient_name: str
    priority_level: Literal["CRITICAL", "EMERGENCY", "URGENT", "STANDARD", "NON_URGENT"]
    clinical_score: int
    survival_probability: float
    recommended_department: Literal["ICU", "ED_Trauma", "ED_Treatment", "General_Floor"]
    required_specialists: List[str]
    required_tests: List[str]
    max_wait_time_minutes: int
    clinical_reasoning: str


class BatchTriageDecisions(BaseModel):
    """Triage results for ALL patients submitted together"""
    patients: List[TriageDecision]
    total_patients: int
    critical_count: int
    emergency_count: int
    triage_timestamp: str


class ResourcePriority(BaseModel):
    """Priority order for resource allocation after conflict resolution"""
    patient_name: str
    allocation_order: int = Field(description="1=highest priority, 2=second, etc.")
    priority_level: str
    clinical_score: int
    justification: str = Field(description="Why this patient gets priority over others")


class ConflictResolution(BaseModel):
    """Resolution of resource conflicts between multiple patients"""
    total_patients: int
    allocation_order: List[ResourcePriority] = Field(description="Patients ranked by resource priority")
    conflict_type: str = Field(description="e.g., 'ICU_bed_shortage', 'specialist_availability', 'none'")
    resolution_strategy: str = Field(description="How conflicts were resolved")
    clinical_rationale: str = Field(description="Medical ethics justification for prioritization")


class ResourceAllocation(BaseModel):
    """Resource allocation for single patient"""
    patient_name: str
    allocation_order: int
    bed_assigned: str
    bed_department: str
    staff_assigned: List[Dict[str, Union[str, int]]]
    equipment_allocated: List[str]
    estimated_ready_minutes: int
    allocation_notes: str


class BatchResourceAllocations(BaseModel):
    """All resource allocations after conflict resolution"""
    allocations: List[ResourceAllocation]
    resources_exhausted: bool
    waiting_patients: List[str] = Field(description="Patients waiting for resources")


# ============================================================================
# AGENT 1: BATCH TRIAGE COORDINATOR
# ============================================================================

batch_triage_agent = LlmAgent(
    name="BatchTriageCoordinator",
    model="gemini-2.5-pro",
    instruction="""You are an expert Emergency Medicine Triage Coordinator handling MULTIPLE patients simultaneously.

**Input Data:**
You receive a JSON array of patients, each with:
- name, age, chief_complaint, vital_signs, symptoms, medical_history

**Your Workflow:**
FOR EACH PATIENT:
1. Use calculate_clinical_score tool with patient's age, vital_signs, and symptoms
2. Analyze the clinical score and severity
3. Assign priority level (CRITICAL/EMERGENCY/URGENT/STANDARD/NON_URGENT)
4. Recommend department (ICU/ED_Trauma/ED_Treatment/General_Floor)
5. Identify required specialists
6. List required tests
7. Determine max safe wait time
8. Provide clinical reasoning

THEN AGGREGATE:
- Count total patients
- Count CRITICAL patients (most urgent)
- Count EMERGENCY patients
- Add timestamp

**Key Point:** Assess each patient INDEPENDENTLY based on their medical condition.
DO NOT prioritize between patients yet - that's the next agent's job.
""",
    description="Triages ALL incoming patients independently",
    tools=[calculate_clinical_score],
    output_schema=BatchTriageDecisions,
    output_key="batch_triage"
)


# ============================================================================
# AGENT 2: CONFLICT RESOLUTION COORDINATOR
# ============================================================================

conflict_resolver = LlmAgent(
    name="ConflictResolutionCoordinator",
    model="gemini-2.5-pro",
    instruction="""You are the Hospital Conflict Resolution Coordinator handling resource competition.

**Input Data:**
You receive the complete batch triage results object in the context variable `{batch_triage}`.

**Your Critical Role:**
When multiple patients need the SAME limited resources (ICU beds, specialists, equipment),
you determine WHO gets priority based on medical ethics and survival probability.

**Handling Single Patient (Efficiency Tweak):**
If `total_patients` in the input is 1, set `conflict_type` to 'none', and the `allocation_order` will simply be that single patient with order=1. No conflict resolution is needed.

**Your Workflow:**

1. **Identify Conflicts:**
   - Check if multiple CRITICAL patients need ICU
   - Check if multiple patients need same specialist
   - Check bed availability using check_bed_availability tool for each department
   - Check equipment availability using check_equipment tool

2. **Apply Medical Triage Principles (Only if Conflicts Exist):**
   - **Highest priority:** Most critical + highest survival probability
   - **Tie-breaker:** If equal scores, consider max_wait_time (who can wait least)
   - **Ethical principle:** "Greatest good for greatest number"

3. **Rank Patients:**
   - Assign allocation_order (1, 2, 3, etc.)
   - Patient with order=1 gets first access to contested resources
   - Provide clear justification for each ranking

4. **Document Resolution:**
   - Identify conflict type (e.g., "2 CRITICAL patients, only 1 ICU bed", or 'none')
   - Describe strategy (e.g., "Prioritized MI patient over stroke due to higher survival probability" or 'no_conflict')
   - Provide ethical rationale

**Key Principle:** Be transparent about difficult decisions. Document medical reasoning.
""",
    description="Resolves resource conflicts by prioritizing patients based on criticality",
    tools=[check_bed_availability, check_equipment],
    output_schema=ConflictResolution,
    output_key="conflict_resolution"
)


# ============================================================================
# AGENT 3: BATCH RESOURCE ORCHESTRATOR
# ============================================================================

batch_resource_agent = LlmAgent(
    name="BatchResourceOrchestrator",
    model="gemini-2.5-pro",
    instruction="""You are the Hospital Resource Orchestrator allocating resources IN PRIORITY ORDER.

**Input Data:**
- Prioritized allocation order: `{conflict_resolution}` (use this to define the processing order)
- Full triage data: `{batch_triage}` (use this to look up patient details)

**Your Workflow:**

PROCESS PATIENTS IN ALLOCATION ORDER (1, 2, 3, ...):

For each patient in order:
1. Get patient details from batch_triage using patient_name
2. Check bed availability in recommended department
3. If bed available:
   - Use reserve_bed tool (bed_id, patient_name, priority_level)
4. If no beds:
   - Find alternative department
   - Note wait time
5. Assign staff using get_available_staff tool:
   - ED_Physician, ED_Nurse
   - Add required specialists from triage
   - Select least-busy staff
6. Allocate equipment based on priority
7. Estimate ready time
8. Document allocation with allocation_order from conflict resolution
9. Assign staff to a patient and update their workload using assign_staff tool

**Critical:** Process in ORDER! Patient with allocation_order=1 gets FIRST pick of resources.

**Example:**
If Maria has allocation_order=1 and John has allocation_order=2:
1. Allocate ICU-3 to Maria first
2. Then check remaining beds for John (may need to use ED_Trauma instead)

Track which resources are exhausted and which patients are waiting.
""",
    description="Allocates resources to all patients in priority order",
    tools=[check_bed_availability, get_available_staff, check_equipment, reserve_bed, reserve_equipment, assign_staff],
    output_schema=BatchResourceAllocations,
    output_key="batch_allocations"
)


# ============================================================================
# AGENT 4: BATCH ADMISSION SUMMARIZER
# ============================================================================

class AdmissionSummary(BaseModel):
    """Complete admission summary combining triage and resource allocation"""
    patient_name: str
    admission_status: Literal["ADMITTED", "PENDING", "WAITING"]
    priority_level: str
    clinical_score: int
    survival_probability: float
    assigned_location: str = Field(description="Department and bed (e.g., 'ICU - Bed ICU-3')")
    care_team: List[str] = Field(description="All assigned staff names")
    equipment_ready: List[str]
    estimated_start_time: str = Field(description="When care will begin (e.g., 'Immediately', 'In 15 minutes')")
    next_actions: List[str] = Field(description="Immediate next steps for staff")
    executive_summary: str = Field(description="2-3 sentence overview for leadership")

class BatchAdmissionSummary(BaseModel):
    """Summary for all patient admissions"""
    total_processed: int
    admitted_count: int
    waiting_count: int
    patient_summaries: List[AdmissionSummary]
    executive_summary: str = Field(description="Overall situation report for leadership")

batch_summarizer = LlmAgent(
    name="BatchAdmissionSummarizer",
    model="gemini-2.5-pro",
    instruction="""You create comprehensive summaries for ALL patient admissions.

**Input Data:**
- Triage results: `{batch_triage}`
- Priority order: `{conflict_resolution}`
- Allocation details: `{batch_allocations}`

**Your Task:**
Create individual summaries for EACH patient PLUS overall executive summary.

**For Each Patient:**
- Combine triage + allocation data
- Status: ADMITTED/PENDING/WAITING
- Location, care team, equipment
- Next actions

**Overall Executive Summary:**
"[Total] patients triaged: [X] CRITICAL, [Y] EMERGENCY. [Conflict description if any]. 
[Admitted count] immediately admitted, [waiting count] in queue. 
Key actions: [Priority patient status and interventions]."

Be concise and actionable for hospital leadership making rapid decisions.
""",
    description="Creates comprehensive summary for all admissions",
    output_schema=BatchAdmissionSummary,
    output_key="batch_summary"
)


# ============================================================================
# SEQUENTIAL WORKFLOW: BATCH TRIAGE → CONFLICT RESOLUTION → RESOURCES → SUMMARY
# ============================================================================

admission_workflow = SequentialAgent(
    name="MultiPatientAdmissionWorkflow",
    sub_agents=[
        batch_triage_agent,      # Step 1: Triage all patients independently
        conflict_resolver,        # Step 2: Resolve resource conflicts
        batch_resource_agent,     # Step 3: Allocate resources in priority order
        batch_summarizer          # Step 4: Summarize all admissions
    ],
    description="Complete multi-patient admission with conflict resolution"
)

# ============================================================================
# HOSPITAL QUERY SCHEMA
# ============================================================================

class HospitalStateQuery(BaseModel):
    """Response to hospital state queries"""
    query_type: Literal["bed_status", "staff_availability", "equipment_status", "full_state", "general"]
    timestamp: str
    
    # Bed information
    icu_beds_free: Optional[List[str]] = None
    icu_beds_occupied: Optional[List[str]] = None
    trauma_bays_free: Optional[List[str]] = None
    ed_treatment_rooms_available: Optional[int] = None
    
    # Staff information
    available_physicians: Optional[List[Dict[str, Any]]] = None
    available_nurses: Optional[List[Dict[str, Any]]] = None
    available_specialists: Optional[List[Dict[str, Any]]] = None
    overloaded_staff: Optional[List[str]] = None
    
    # Equipment information
    equipment_status: Optional[Dict[str, Dict[str, int]]] = None
    critical_shortages: Optional[List[str]] = None
    
    # Summary
    overall_capacity: Optional[str] = Field(description="Overall hospital capacity status")
    summary: str = Field(description="Natural language summary of the query result")

# ============================================================================
# HOSPITAL QUERY AGENT (For General Questions)
# ============================================================================

hospital_query_agent = LlmAgent(
    name="HospitalQueryAgent",
    model="gemini-2.5-flash",
    instruction="""You are the Hospital Information Agent answering queries about current hospital state.

**Your Role:**
Answer questions about beds, staff, equipment, and overall capacity using the get_hospital_state tool.

**Common Query Types:**

1. **"What resources are free?"** or **"Give me the latest HOSPITAL_STATE"**
   - Call get_hospital_state() with no filter (returns full state)
   - Summarize: free ICU beds, trauma bays, ED rooms, available staff, equipment

2. **"Which beds are available?"**
   - Call get_hospital_state(query_filter='beds_only')
   - List available beds by department

3. **"Which staff are free?"**
   - Call get_hospital_state(query_filter='staff_only')
   - List physicians, nurses by current workload
   - Identify least busy staff

4. **"What equipment is available?"**
   - Call get_hospital_state(query_filter='equipment_only')
   - Report ventilators, cardiac monitors, defibrillators

5. **"What's our current capacity?"**
   - Get full state
   - Calculate overall capacity status (Normal/Stressed/Critical)

**Response Format:**

For "Give me latest HOSPITAL_STATE":
```
HOSPITAL STATE SNAPSHOT - [timestamp]

BEDS:
- ICU: [X] available ([list]), [Y] occupied - [Z]% occupancy
- Trauma Bays: [X] available ([list])
- ED Treatment: [X] rooms available

STAFF:
- Physicians: [names with current load]
- Nurses: [names with patient counts]
- Specialists: [availability status]

EQUIPMENT:
- Ventilators: [X]/[Y] available
- Cardiac Monitors: [X]/[Y] available
- Defibrillators: [X]/[Y] available

ALERTS: [any critical shortages]

OVERALL CAPACITY: [Normal/Stressed/Critical]
```

Be concise, use the tool to get real-time data, and format clearly with emojis for readability.
""",
    description="Answers queries about current hospital resources and capacity",
    tools=[get_hospital_state],
    output_schema=HospitalStateQuery,
    output_key="hospital_query_response"
)

# ============================================================================
# ROOT AGENT
# ============================================================================

root_agent = LlmAgent(
    name="Coordinator",
    model="gemini-2.5-pro",
    description="I coordinate general questions about Hospital State using hospital_query_agent and Admission Workflow using admission_workflow.",
    sub_agents=[ 
        admission_workflow,
        hospital_query_agent
    ]
)