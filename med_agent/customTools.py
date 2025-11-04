from typing import Literal, Optional, List, Dict, Any
from datetime import datetime, timedelta
import json

# ============================================================================
# HOSPITAL STATE & TOOLS
# ============================================================================

HOSPITAL_STATE = {
    'icu_beds': {
        'ICU-1': {'status': 'occupied', 'patient': 'P001', 'expected_discharge': '2024-10-30T14:00'},
        'ICU-2': {'status': 'occupied', 'patient': 'P002', 'expected_discharge': '2024-10-30T08:00'},
        'ICU-3': {'status': 'available', 'patient': None},
        'ICU-4': {'status': 'available', 'patient': None},
    },
    'ed_trauma_bays': {
        'TB-1': {'status': 'occupied', 'patient': 'P003'},
        'TB-2': {'status': 'available', 'patient': None},
        'TB-3': {'status': 'available', 'patient': None},
    },
    'ed_treatment_rooms': {'available': 5, 'total': 15, 'occupied': 10},
    'staff_available': {
        'ed_physicians': [
            {'name': 'Dr. Smith', 'specialty': 'Emergency Medicine', 'current_load': 3},
            {'name': 'Dr. Jones', 'specialty': 'Emergency Medicine', 'current_load': 2},
        ],
        'ed_nurses': [
            {'name': 'RN Johnson', 'current_patients': 4},
            {'name': 'RN Williams', 'current_patients': 3},
            {'name': 'RN Davis', 'current_patients': 2}
        ],
        'cardiologists': [{'name': 'Dr. Patel', 'available': True}],
        'trauma_surgeons': [{'name': 'Dr. Martinez', 'available': True}],
    },
    'equipment': {
        'ventilators': {'available': 2, 'total': 7},
        'cardiac_monitors': {'available': 8, 'total': 15},
        'defibrillators': {'available': 6, 'total': 8},
    }
}


def get_hospital_state(query_filter: Optional[str] = None) -> Dict:
    """
    Get current hospital state - beds, staff, equipment
    
    Args:
        query_filter: Optional filter like 'beds_only', 'staff_only', 'equipment_only', or None for full state
    
    Returns:
        Current hospital state filtered by query
    """
    state_snapshot = {
        'timestamp': datetime.now().isoformat(),
        'query_filter': query_filter or 'full_state'
    }
    
    if query_filter in [None, 'beds_only', 'full_state']:
        # ICU beds
        icu_available = [bed_id for bed_id, data in HOSPITAL_STATE['icu_beds'].items() 
                         if data['status'] == 'available']
        icu_occupied = [bed_id for bed_id, data in HOSPITAL_STATE['icu_beds'].items() 
                        if data['status'] in ['occupied', 'reserved']]
        
        # Trauma bays
        trauma_available = [bed_id for bed_id, data in HOSPITAL_STATE['ed_trauma_bays'].items() 
                           if data['status'] == 'available']
        trauma_occupied = [bed_id for bed_id, data in HOSPITAL_STATE['ed_trauma_bays'].items() 
                          if data['status'] in ['occupied', 'reserved']]
        
        state_snapshot['beds'] = {
            'icu': {
                'available': icu_available,
                'available_count': len(icu_available),
                'occupied': icu_occupied,
                'occupied_count': len(icu_occupied),
                'total': len(HOSPITAL_STATE['icu_beds']),
                'occupancy_rate': len(icu_occupied) / len(HOSPITAL_STATE['icu_beds']) * 100
            },
            'trauma_bays': {
                'available': trauma_available,
                'available_count': len(trauma_available),
                'occupied': trauma_occupied,
                'occupied_count': len(trauma_occupied),
                'total': len(HOSPITAL_STATE['ed_trauma_bays'])
            },
            'ed_treatment': HOSPITAL_STATE['ed_treatment_rooms']
        }
    
    if query_filter in [None, 'staff_only', 'full_state']:
        state_snapshot['staff'] = {
            'physicians': HOSPITAL_STATE['staff_available']['ed_physicians'],
            'nurses': HOSPITAL_STATE['staff_available']['ed_nurses'],
            'specialists': {
                'cardiologists': HOSPITAL_STATE['staff_available']['cardiologists'],
                'trauma_surgeons': HOSPITAL_STATE['staff_available']['trauma_surgeons']
            },
            'physician_workload_summary': {
                'least_busy': min((p['current_load'] for p in HOSPITAL_STATE['staff_available']['ed_physicians']), default=0),
                'most_busy': max((p['current_load'] for p in HOSPITAL_STATE['staff_available']['ed_physicians']), default=0),
                'average_load': sum(p['current_load'] for p in HOSPITAL_STATE['staff_available']['ed_physicians']) / len(HOSPITAL_STATE['staff_available']['ed_physicians'])
            }
        }
    
    if query_filter in [None, 'equipment_only', 'full_state']:
        state_snapshot['equipment'] = HOSPITAL_STATE['equipment']
        
        # Identify shortages
        shortages = []
        for equip_type, data in HOSPITAL_STATE['equipment'].items():
            utilization = (data['total'] - data['available']) / data['total'] * 100
            if data['available'] == 0:
                shortages.append(f"{equip_type}: NONE AVAILABLE")
            elif utilization >= 80:
                shortages.append(f"{equip_type}: {data['available']}/{data['total']} available ({utilization:.0f}% utilized)")
        
        state_snapshot['equipment_shortages'] = shortages
    
    return state_snapshot

# ============================================================================
# TOOLS FOR AGENTS
# ============================================================================

def calculate_clinical_score(
    age: int,
    vital_signs: Dict[str, float],
    symptoms: List[str]
) -> Dict[str, Any]:
    """
    Calculate clinical severity score (0-20 scale, APACHE-like)
    Higher score = more severe
    
    Args:
        age: Patient age in years
        vital_signs: Dict with heart_rate, bp_systolic, oxygen_saturation
        symptoms: List of symptom strings
    
    Returns:
        Dict with score, severity level, and risk factors
    """
    score = 0
    risk_factors = []
    
    # Age scoring
    if age > 75:
        score += 3
        risk_factors.append(f"Advanced age ({age}y)")
    elif age > 65:
        score += 2
        risk_factors.append(f"Elderly ({age}y)")
    elif age < 1:
        score += 2
        risk_factors.append("Infant")
    
    # Vital signs
    hr = vital_signs.get('heart_rate', 80)
    bp_sys = vital_signs.get('bp_systolic', 120)
    o2_sat = vital_signs.get('oxygen_saturation', 98)
    
    # Heart rate
    if hr > 130 or hr < 50:
        score += 3
        risk_factors.append(f"Critical heart rate ({hr} bpm)")
    elif hr > 110 or hr < 60:
        score += 2
        risk_factors.append(f"Abnormal heart rate ({hr} bpm)")
    
    # Blood pressure
    if bp_sys < 90:
        score += 4
        risk_factors.append(f"Hypotension ({bp_sys} mmHg)")
    elif bp_sys > 180:
        score += 2
        risk_factors.append(f"Severe hypertension ({bp_sys} mmHg)")
    
    # Oxygen saturation
    if o2_sat < 88:
        score += 5
        risk_factors.append(f"Critical hypoxia ({o2_sat}%)")
    elif o2_sat < 92:
        score += 3
        risk_factors.append(f"Hypoxia ({o2_sat}%)")
    elif o2_sat < 95:
        score += 1
        risk_factors.append(f"Low oxygen ({o2_sat}%)")
    
    # Critical symptoms
    critical_keywords = {
        'chest pain': 3,
        'unresponsive': 4,
        'stroke': 4,
        'seizure': 3,
        'severe bleeding': 3,
        'head trauma': 3,
        'difficulty breathing': 2,
        'altered mental': 2
    }
    
    for symptom in symptoms:
        symptom_lower = symptom.lower()
        for keyword, points in critical_keywords.items():
            if keyword in symptom_lower:
                score += points
                risk_factors.append(f"Critical symptom: {symptom}")
                break
    
    # Calculate severity
    if score >= 12:
        severity = "CRITICAL"
        survival_prob = max(40, 95 - (score * 4))
    elif score >= 8:
        severity = "HIGH"
        survival_prob = max(60, 100 - (score * 3))
    elif score >= 5:
        severity = "MODERATE"
        survival_prob = max(80, 100 - (score * 2))
    else:
        severity = "LOW"
        survival_prob = 95
    
    return {
        'clinical_score': score,
        'severity': severity,
        'survival_probability': survival_prob,
        'risk_factors': risk_factors,
        'calculation_time': datetime.now().isoformat()
    }


def check_bed_availability(department: Literal["ICU", "ED_Trauma", "ED_Treatment"]) -> dict:
    """Check real-time bed availability (excluding reserved beds)"""
    
    if department == "ICU":
        # FIX: Exclude both 'occupied' AND 'reserved'
        available = [bed_id for bed_id, data in HOSPITAL_STATE['icu_beds'].items() 
                     if data['status'] == 'available']
        
        reserved = [bed_id for bed_id, data in HOSPITAL_STATE['icu_beds'].items() 
                    if data['status'] == 'reserved']
        
        return {
            'department': 'ICU',
            'available_beds': available,
            'reserved_beds': reserved,  # NEW: Show what's reserved
            'count': len(available),
            'total_beds': len(HOSPITAL_STATE['icu_beds']),
            'occupancy_rate': (len(HOSPITAL_STATE['icu_beds']) - len(available)) / len(HOSPITAL_STATE['icu_beds']) * 100,
            'estimated_wait_minutes': 0 if available else 45
        }
    
    elif department == "ED_Trauma":
        available = [bed_id for bed_id, data in HOSPITAL_STATE['ed_trauma_bays'].items() 
                     if data['status'] == 'available']
        
        reserved = [bed_id for bed_id, data in HOSPITAL_STATE['ed_trauma_bays'].items() 
                    if data['status'] == 'reserved']
        
        return {
            'department': 'ED_Trauma',
            'available_beds': available,
            'reserved_beds': reserved,  # NEW
            'count': len(available),
            'total_beds': len(HOSPITAL_STATE['ed_trauma_bays']),
            'estimated_wait_minutes': 0 if available else 20
        }
    
    elif department == "ED_Treatment":
        count = HOSPITAL_STATE['ed_treatment_rooms']['available']
        total = HOSPITAL_STATE['ed_treatment_rooms']['total']
        return {
            'department': 'ED_Treatment',
            'available_beds': f"{count} treatment rooms",
            'count': count,
            'total_beds': total,
            'occupancy_rate': (total - count) / total * 100,
            'estimated_wait_minutes': 0 if count > 0 else 35
        }


def get_available_staff(specialty: Literal["ED_Physician", "ED_Nurse", "Cardiologist", "Trauma_Surgeon"]) -> dict:
    """
    Get available staff by specialty, sorted by current workload
    
    Args:
        specialty: Type of medical staff needed
    
    Returns:
        Dict with staff list sorted by availability
    """
    specialty_map = {
        "ED_Physician": 'ed_physicians',
        "ED_Nurse": 'ed_nurses',
        "Cardiologist": 'cardiologists',
        "Trauma_Surgeon": 'trauma_surgeons'
    }
    
    key = specialty_map.get(specialty)
    if not key:
        return {'error': f'Unknown specialty: {specialty}', 'available_staff': []}
    
    staff_list = HOSPITAL_STATE['staff_available'].get(key, [])
    
    # Sort by workload (least busy first)
    if key == 'ed_physicians':
        sorted_staff = sorted(staff_list, key=lambda x: x.get('current_load', 0))
    elif key == 'ed_nurses':
        sorted_staff = sorted(staff_list, key=lambda x: x.get('current_patients', 0))
    else:
        sorted_staff = [s for s in staff_list if s.get('available', True)]
    
    return {
        'specialty': specialty,
        'available_staff': sorted_staff,
        'total_count': len(sorted_staff),
        'least_busy': sorted_staff[0] if sorted_staff else None
    }


def check_equipment(equipment_type: Literal["ventilators", "cardiac_monitors", "defibrillators"]) -> dict:
    """
    Check equipment availability
    
    Args:
        equipment_type: Type of equipment
    
    Returns:
        Equipment status and availability
    """
    equipment = HOSPITAL_STATE['equipment'].get(equipment_type, {})
    available = equipment.get('available', 0)
    total = equipment.get('total', 0)
    
    return {
        'equipment_type': equipment_type,
        'available': available,
        'total': total,
        'in_use': total - available,
        'utilization_rate': (total - available) / total * 100 if total > 0 else 0,
        'status': 'available' if available > 0 else 'all_in_use'
    }


def reserve_bed(bed_id: str, patient_name: str, priority: str) -> dict:
    """Reserve a specific bed for a patient"""
    reservation_time = datetime.now().isoformat()
    
    # Reserve ICU bed
    if bed_id in HOSPITAL_STATE['icu_beds']:
        current_status = HOSPITAL_STATE['icu_beds'][bed_id]['status']
        
        # FIX: Check if already reserved by someone else
        if current_status == 'reserved':
            current_patient = HOSPITAL_STATE['icu_beds'][bed_id].get('patient')
            return {
                'success': False,
                'bed_id': bed_id,
                'message': f'Bed {bed_id} already reserved for {current_patient}'
            }
        
        if current_status == 'available':
            HOSPITAL_STATE['icu_beds'][bed_id] = {
                'status': 'reserved',
                'patient': patient_name,
                'priority': priority,
                'reserved_at': reservation_time
            }
            return {
                'success': True,
                'bed_id': bed_id,
                'department': 'ICU',
                'patient': patient_name,
                'message': f'ICU bed {bed_id} reserved for {patient_name}'
            }
        else:
            return {
                'success': False,
                'bed_id': bed_id,
                'message': f'Bed {bed_id} not available (status: {current_status})'
            }
    
    # Reserve trauma bay
    elif bed_id in HOSPITAL_STATE['ed_trauma_bays']:
        current_status = HOSPITAL_STATE['ed_trauma_bays'][bed_id]['status']
        
        if current_status == 'reserved':
            current_patient = HOSPITAL_STATE['ed_trauma_bays'][bed_id].get('patient')
            return {
                'success': False,
                'bed_id': bed_id,
                'message': f'Trauma bay {bed_id} already reserved for {current_patient}'
            }
        
        if current_status == 'available':
            HOSPITAL_STATE['ed_trauma_bays'][bed_id] = {
                'status': 'reserved',
                'patient': patient_name,
                'priority': priority,
                'reserved_at': reservation_time
            }
            return {
                'success': True,
                'bed_id': bed_id,
                'department': 'ED_Trauma',
                'patient': patient_name,
                'message': f'Trauma bay {bed_id} reserved for {patient_name}'
            }
        else:
            return {
                'success': False,
                'bed_id': bed_id,
                'message': f'Trauma bay {bed_id} not available (status: {current_status})'
            }
    
    return {
        'success': False,
        'bed_id': bed_id,
        'message': f'Bed ID {bed_id} not found in system'
    }


def reserve_equipment(equipment_type: Literal["ventilators", "cardiac_monitors", "defibrillators"], 
                      patient_name: str, 
                      quantity: int = 1) -> dict:
    """
    Reserve equipment for a patient
    
    Args:
        equipment_type: Type of equipment
        patient_name: Patient name
        quantity: Number of units needed
    
    Returns:
        Reservation confirmation
    """
    if equipment_type not in HOSPITAL_STATE['equipment']:
        return {
            'success': False,
            'message': f'Unknown equipment type: {equipment_type}'
        }
    
    equipment = HOSPITAL_STATE['equipment'][equipment_type]
    available = equipment['available']
    
    if available < quantity:
        return {
            'success': False,
            'equipment_type': equipment_type,
            'requested': quantity,
            'available': available,
            'message': f'Insufficient {equipment_type} - only {available} available'
        }
    
    # Reserve the equipment
    HOSPITAL_STATE['equipment'][equipment_type]['available'] -= quantity
    
    return {
        'success': True,
        'equipment_type': equipment_type,
        'quantity_reserved': quantity,
        'patient': patient_name,
        'remaining_available': HOSPITAL_STATE['equipment'][equipment_type]['available'],
        'message': f'{quantity} {equipment_type} reserved for {patient_name}'
    }


def assign_staff(staff_name: str, specialty: str, patient_name: str) -> dict:
    """
    Assign staff to a patient and update their workload
    
    Args:
        staff_name: Staff member name
        specialty: Their specialty
        patient_name: Patient name
    
    Returns:
        Assignment confirmation
    """
    specialty_map = {
        "ED_Physician": 'ed_physicians',
        "ED_Nurse": 'ed_nurses',
        "Cardiologist": 'cardiologists',
        "Trauma_Surgeon": 'trauma_surgeons'
    }
    
    key = specialty_map.get(specialty)
    if not key:
        return {'success': False, 'message': f'Unknown specialty: {specialty}'}
    
    staff_list = HOSPITAL_STATE['staff_available'].get(key, [])
    
    # Find the staff member
    staff_member = next((s for s in staff_list if s['name'] == staff_name), None)
    
    if not staff_member:
        return {'success': False, 'message': f'{staff_name} not found in {specialty}'}
    
    # Update workload
    if key == 'ed_physicians':
        staff_member['current_load'] = staff_member.get('current_load', 0) + 1
    elif key == 'ed_nurses':
        staff_member['current_patients'] = staff_member.get('current_patients', 0) + 1
    else:
        staff_member['available'] = False  # Mark specialists as busy
    
    return {
        'success': True,
        'staff_name': staff_name,
        'specialty': specialty,
        'patient': patient_name,
        'new_load': staff_member.get('current_load') or staff_member.get('current_patients'),
        'message': f'{staff_name} assigned to {patient_name}'
    }


# ============================================================================
# CONFLICT RESOLVER TOOL
# ============================================================================

def detect_resource_conflicts() -> Dict:
    """
    Detect if there are resource conflicts in the hospital
    Checks bed availability, staff workload, equipment shortages
    
    Returns:
        Dict with conflict status and details
    """
    conflicts = []
    conflict_severity = "NONE"
    
    # Check ICU bed conflicts
    icu_available = sum(1 for bed in HOSPITAL_STATE['icu_beds'].values() if bed['status'] == 'available')
    icu_total = len(HOSPITAL_STATE['icu_beds'])
    icu_occupancy = (icu_total - icu_available) / icu_total * 100
    
    if icu_occupancy >= 90:
        conflicts.append({
            'type': 'ICU_CAPACITY',
            'severity': 'CRITICAL',
            'details': f'ICU at {icu_occupancy:.0f}% capacity - only {icu_available} beds available',
            'recommendation': 'Consider ED holding or transfer to partner facility'
        })
        conflict_severity = "CRITICAL"
    elif icu_occupancy >= 75:
        conflicts.append({
            'type': 'ICU_CAPACITY',
            'severity': 'HIGH',
            'details': f'ICU at {icu_occupancy:.0f}% capacity',
            'recommendation': 'Monitor for potential shortage'
        })
        if conflict_severity != "CRITICAL":
            conflict_severity = "HIGH"
    
    # Check ED trauma bay conflicts
    trauma_available = sum(1 for bay in HOSPITAL_STATE['ed_trauma_bays'].values() if bay['status'] == 'available')
    trauma_total = len(HOSPITAL_STATE['ed_trauma_bays'])
    
    if trauma_available == 0:
        conflicts.append({
            'type': 'TRAUMA_BAY_SHORTAGE',
            'severity': 'HIGH',
            'details': 'No trauma bays available',
            'recommendation': 'Use ED treatment rooms for non-trauma critical patients'
        })
        if conflict_severity not in ["CRITICAL", "HIGH"]:
            conflict_severity = "HIGH"
    
    # Check staff workload
    physicians_overloaded = [p for p in HOSPITAL_STATE['staff_available']['ed_physicians'] 
                             if p.get('current_load', 0) >= 5]
    if physicians_overloaded:
        conflicts.append({
            'type': 'PHYSICIAN_OVERLOAD',
            'severity': 'MODERATE',
            'details': f'{len(physicians_overloaded)} physicians at capacity (5+ patients)',
            'recommendation': 'Redistribute new admissions or call additional staff'
        })
        if conflict_severity == "NONE":
            conflict_severity = "MODERATE"
    
    # Check equipment shortages
    ventilators_available = HOSPITAL_STATE['equipment']['ventilators']['available']
    if ventilators_available == 0:
        conflicts.append({
            'type': 'VENTILATOR_SHORTAGE',
            'severity': 'CRITICAL',
            'details': 'No ventilators available',
            'recommendation': 'Use BiPAP or manual ventilation; prepare for transfer'
        })
        conflict_severity = "CRITICAL"
    elif ventilators_available <= 1:
        conflicts.append({
            'type': 'VENTILATOR_LIMITED',
            'severity': 'HIGH',
            'details': f'Only {ventilators_available} ventilator(s) available',
            'recommendation': 'Reserve for most critical patients only'
        })
        if conflict_severity not in ["CRITICAL"]:
            conflict_severity = "HIGH"
    
    return {
        'conflicts_detected': len(conflicts) > 0,
        'conflict_count': len(conflicts),
        'severity': conflict_severity,
        'conflicts': conflicts,
        'timestamp': datetime.now().isoformat(),
        'requires_intervention': conflict_severity in ["CRITICAL", "HIGH"]
    }


def propose_conflict_resolution(
    patient_name: str,
    priority_level: str,
    resource_type: str,
    justification: str
) -> Dict:
    """
    Submit a proposal for resolving resource conflict
    Used when multiple patients need same scarce resource
    
    Args:
        patient_name: Patient identifier
        priority_level: Triage priority (CRITICAL, EMERGENCY, etc.)
        resource_type: Type of resource needed (ICU_bed, ventilator, etc.)
        justification: Medical reasoning for resource allocation
    
    Returns:
        Proposal confirmation
    """
    proposal = {
        'proposal_id': f"PROP-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        'timestamp': datetime.now().isoformat(),
        'patient': patient_name,
        'priority': priority_level,
        'resource_requested': resource_type,
        'justification': justification,
        'status': 'submitted'
    }
    
    # In production, this would be logged to database for review
    print(f"[CONFLICT PROPOSAL] {proposal['proposal_id']} - {patient_name} requesting {resource_type}")
    
    return {
        'success': True,
        'proposal': proposal,
        'message': f'Conflict resolution proposal submitted for {patient_name}'
    }


def log_agent_message(recipient: str, message: str, priority: str) -> dict:
    """
    Logs a communication/notification in the system
    
    Args:
        recipient: Who receives the message (staff name, department, or role)
        message: The notification content
        priority: ROUTINE, URGENT, or CRITICAL
    
    Returns:
        Confirmation of logged message
    """
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "recipient": recipient,
        "message": message,
        "priority": priority,
        "status": "SENT"
    }
    
    # In production, this would send to notification system
    # For now, just return confirmation
    print(f"[{priority}] TO {recipient}: {message}")
    
    return {
        "success": True,
        "log_entry": log_entry,
        "message": f"Notification sent to {recipient}"
    }