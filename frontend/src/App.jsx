import React, { useState, useEffect, useMemo, useRef } from 'react';
import localOpportunityDataset from '../../data/opportunities.json';
import { DEMO_REFERENCE_DATE, OPPORTUNITY_CATEGORIES, readOpportunities, evaluateDeadline, formatDate, displayValue } from './opportunityData.js';
import { ELIGIBILITY_STATES, adaptEligibilityResults, emptyEligibility, matchesProfileSnapshot, presentCondition, summarizeConditions } from './eligibilityResults.js';

/**
 * ==============================================================================
 * FUTUREPATH AU - CYBERSECURITY CAREER PATHWAY PROTOTYPE
 * Team Member: Hakm (Frontend Lead)
 * Tasks Covered: [HAK-01] to [HAK-06]
 *
 * LOCKED PROJECT CONSTRAINTS (MANDATORY SAFEGUARDS):
 * 1. No Autonomous Applications: The system guides and plans; it NEVER automatically
 *    submits job or study applications. Applications must be student-initiated.
 * 2. No Identity Scoring: Suitability is NEVER inferred or scored using Indigenous
 *    identity. Only documented, published eligibility criteria are evaluated.
 * 3. Deterministic Fact-Grounded Data: Opportunity titles, providers, prerequisites,
 *    deadlines, URLs, and checked dates are source-grounded facts.
 * 4. Human Oversight: The user retains full agency to edit, reorder, delete, and
 *    explicitly approve their pathway plan before it is marked final.
 * ==============================================================================
 */

// Vite bundles the shared source JSON in development and production. No copied dataset.
const LOCAL_OPPORTUNITIES = readOpportunities(localOpportunityDataset);

const EMPTY_STEP_EDIT = { title: '', description: '', timeline: '' };
const EMPTY_CUSTOM_STEP = {
  phase: 'Milestone 2: Application Preparation', title: '', description: '', timeline: 'Weeks 5 - 6'
};

const initialProfile = {
  education_level: 'not_stated',
  enrolment_status: 'not_stated',
  institution: '',
  citizenship_status: 'not_stated',
  state: 'not_stated',
  field_of_study: '',
  weighted_average: null,
  skills: [],
  experience_notes: '',
  preferred_agencies: [],
  identity_answer: 'not_stated'
};

const PROFILE_OPTIONS = {
  education_level: ['undergraduate', 'postgraduate', 'vocational', 'school_leaver', 'graduate', 'not_stated'],
  enrolment_status: ['enrolled_full_time', 'enrolled_part_time', 'commencing', 'not_enrolled', 'not_stated'],
  citizenship_status: ['australian_citizen', 'permanent_resident', 'nz_citizen', 'other', 'not_stated'],
  state: ['ACT', 'NSW', 'NT', 'QLD', 'SA', 'TAS', 'VIC', 'WA', 'not_stated'],
  identity_answer: ['yes', 'no', 'prefer_not_to_say', 'not_stated']
};

const PROFILE_LABELS = {
  education_level: 'Education Level',
  enrolment_status: 'Enrolment Status',
  citizenship_status: 'Citizenship Status',
  state: 'State',
  identity_answer: 'Aboriginal and/or Torres Strait Islander Identity (voluntary)'
};

// Curated catalog of standard cybersecurity skills for [HAK-02] dropdown selector
const CYBER_SKILLS_CATALOG = [
  {
    category: 'Agreed Profile Skill Tags',
    skills: ['cyber security', 'technology', 'ICT', 'software engineering', 'digital', 'STEM', 'data', 'digital delivery', 'computing', 'data science', 'networking', 'cybernetics']
  },
  {
    category: 'Core Cyber Security & Analysis',
    skills: [
      'Networking',
      'Wireshark',
      'Packet Analysis',
      'SIEM Basics',
      'Incident Response',
      'Vulnerability Assessment',
      'Digital Forensics',
      'Threat Intelligence'
    ]
  },
  {
    category: 'Operating Systems & Command Line',
    skills: [
      'Linux',
      'Command Line / Bash',
      'Windows Security',
      'PowerShell',
      'Active Directory'
    ]
  },
  {
    category: 'Programming & Automation',
    skills: [
      'Python',
      'C++',
      'Bash Scripting',
      'Data Analysis',
      'Scripting'
    ]
  },
  {
    category: 'Cloud & Infrastructure',
    skills: [
      'Cloud Computing',
      'AWS',
      'Azure Security',
      'Firewalls',
      'Docker / Containers'
    ]
  },
  {
    category: 'Foundations & Governance',
    skills: [
      'Security Principles',
      'TCP/IP',
      'Risk Management',
      'Cryptography'
    ]
  }
];

// Modern, crisp SVG icons replacing OS/browser emoji characters
function IconLock({ size = 18, className = "" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

function IconScales({ size = 18, className = "" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="m16 16 3-8 3 8a3 3 0 0 1-6 0v0Z" />
      <path d="m2 16 3-8 3 8a3 3 0 0 1-6 0v0Z" />
      <path d="M7 21h10" />
      <path d="M12 3v18" />
      <path d="M3 7h18" />
    </svg>
  );
}

function IconFileVerified({ size = 18, className = "" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <path d="m9 15 2 2 4-4" />
    </svg>
  );
}

function IconUserCheck({ size = 18, className = "" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <polyline points="16 11 18 13 22 9" />
    </svg>
  );
}

function IconAlertTriangle({ size = 20, className = "" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

function IconSearch({ size = 30, className = "" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function IconExternalLink({ size = 13, className = "" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} style={{ verticalAlign: 'middle', marginLeft: '3px' }} aria-hidden="true">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  );
}

function IconCheckCircle({ size = 20, className = "" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}

function IconCompass({ size = 18, className = "" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
    </svg>
  );
}

function IconPrinter({ size = 15, className = "" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} style={{ verticalAlign: 'middle', marginRight: '6px' }} aria-hidden="true">
      <polyline points="6 9 6 2 18 2 18 9" />
      <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
      <rect x="6" y="14" width="12" height="8" />
    </svg>
  );
}

// eligibilityInput is an internal integration seam, not a backend wire contract.
// It stays null in main.jsx until an agreed transport/decoder is implemented.
export default function App({ eligibilityInput = null } = {}) {
  // ---------------------------------------------------------------------------
  // [HAK-02] State: Student Profile & Goal Form
  // ---------------------------------------------------------------------------
  const [profile, setProfile] = useState(initialProfile);
  const [careerGoal, setCareerGoal] = useState(
    'SOC Analyst (Level 1 / Tier 1 Incident Responder)'
  );
  const [customSkill, setCustomSkill] = useState('');
  const [customAgency, setCustomAgency] = useState('');
  const [agencyOptions, setAgencyOptions] = useState(['Defence']);
  const [weightedAverageInvalid, setWeightedAverageInvalid] = useState(false);
  const [formErrors, setFormErrors] = useState({});
  const [profileSubmitted, setProfileSubmitted] = useState(false);

  // Explicit allowlist prevents frontend-only state from entering eligibility data.
  const activeUserProfile = useMemo(() => Object.fromEntries(
    Object.keys(initialProfile).map((field) => [field, profile[field]])
  ), [profile]);
  const selectedSkills = profile.skills;

  const updateProfileField = (field, value) => {
    setProfile((prev) => ({ ...prev, [field]: value }));
    setProfileSubmitted(false);
    setFormErrors((prev) => ({ ...prev, [field]: undefined }));
  };

  const addSkill = (value) => {
    const skill = value.trim();
    if (skill && !selectedSkills.includes(skill)) {
      updateProfileField('skills', [...selectedSkills, skill]);
    }
  };

  const handleSkillSelect = (e) => {
    addSkill(e.target.value);
    e.target.value = '';
  };

  const handleRemoveSkill = (skillToRemove) => {
    updateProfileField('skills', selectedSkills.filter((skill) => skill !== skillToRemove));
  };

  // ---------------------------------------------------------------------------
  // [HAK-03 & HAK-06] State: Opportunities & Backend Connection
  // ---------------------------------------------------------------------------
  const [opportunities, setOpportunities] = useState(LOCAL_OPPORTUNITIES);
  const [isLoading, setIsLoading] = useState(false);
  const [apiError, setApiError] = useState(null);
  const [backendDataSource, setBackendDataSource] = useState('local-development');
  const [datasetNote, setDatasetNote] = useState(localOpportunityDataset.dataset_note);
  const opportunityRequest = useRef(null);

  const eligibility = useMemo(() => {
    if (apiError || eligibilityInput?.unavailable) return emptyEligibility();
    if (eligibilityInput == null) return emptyEligibility();
    if (!matchesProfileSnapshot(eligibilityInput.profileSnapshot, activeUserProfile)) {
      return emptyEligibility('stale', 'Eligibility results do not match the current profile. A new backend evaluation is required.');
    }
    return adaptEligibilityResults(eligibilityInput.payload, opportunities, eligibilityInput.decodeResponse);
  }, [eligibilityInput, activeUserProfile, opportunities, apiError]);

  // Search & Filter state
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('ALL');

  // ---------------------------------------------------------------------------
  // [HAK-06] State: Editable Sequential Career Pathway
  // ---------------------------------------------------------------------------
  const [selectedOpportunityForPathway, setSelectedOpportunityForPathway] = useState(null);
  const [pathwayMilestones, setPathwayMilestones] = useState([
    {
      id: 'step-1',
      phase: 'Milestone 1: Prerequisite Bridging & Eligibility Verification',
      title: 'Complete Practical Networking & Linux Command-Line Fundamentals',
      description: 'Strengthen core prerequisites (TCP/IP, OSI model, packet analysis with Wireshark, and bash scripting) to satisfy entry benchmarks.',
      timeline: 'Weeks 1 - 4',
      status: 'pending',
      actionableUrl: ''
    },
    {
      id: 'step-2',
      phase: 'Milestone 1: Prerequisite Bridging & Eligibility Verification',
      title: 'Review Documentation Requested by the Provider',
      description: 'After choosing an opportunity, check its published conditions and confirm which documents, if any, the provider requests.',
      timeline: 'Weeks 3 - 5',
      status: 'pending',
      actionableUrl: ''
    },
    {
      id: 'step-3',
      phase: 'Milestone 2: Application Submission (Student-Initiated)',
      title: 'Submit Direct Application via Official Provider Portal',
      description: 'Review published opportunity requirements, tailor cyber resume, and submit application directly to the provider (Mandatory safeguard: Platform never submits automatically).',
      timeline: 'Weeks 6 - 8',
      status: 'pending',
      actionableUrl: ''
    },
    {
      id: 'step-4',
      phase: 'Milestone 3: Practical Portfolio & Technical Readiness',
      title: 'Assemble Blue Team Home Lab & Investigation Writeups',
      description: 'Document a home SOC lab (e.g., Security Onion, Splunk Free, or Elastic) analyzing sample malware PCAPs into a student GitHub portfolio.',
      timeline: 'Weeks 9 - 12',
      status: 'pending',
      actionableUrl: ''
    }
  ]);

  // Pathway user controls state
  const [isPathwayApproved, setIsPathwayApproved] = useState(false);
  const [approvedTimestamp, setApprovedTimestamp] = useState(null);
  const [editingStepId, setEditingStepId] = useState(null);
  const [editedStepData, setEditedStepData] = useState(EMPTY_STEP_EDIT);

  // Custom step addition modal/form
  const [showAddStepForm, setShowAddStepForm] = useState(false);
  const [newStep, setNewStep] = useState(EMPTY_CUSTOM_STEP);
  // Synchronous lock and plan version protect against handlers from older renders,
  // including the interval before React commits approval or replacement state.
  const pathwayGuard = useRef({ approved: false, version: 0, editingId: null, nextCustomId: 0 });
  const pathwayVersion = pathwayGuard.current.version;
  const canEditPathway = () => !pathwayGuard.current.approved && pathwayGuard.current.version === pathwayVersion;
  const resetPathwayForms = () => {
    pathwayGuard.current.editingId = null;
    setEditingStepId(null);
    setEditedStepData(EMPTY_STEP_EDIT);
    setShowAddStepForm(false);
    setNewStep(EMPTY_CUSTOM_STEP);
  };
  const updateEditedStep = (field, value) => {
    if (!canEditPathway() || pathwayGuard.current.editingId !== editingStepId) return;
    setEditedStepData((prev) => ({ ...prev, [field]: value }));
  };
  const updateCustomStep = (field, value) => {
    if (!canEditPathway()) return;
    setNewStep((prev) => ({ ...prev, [field]: value }));
  };
  const toggleCustomStepForm = (show) => {
    if (!canEditPathway()) return;
    setShowAddStepForm(show);
    if (!show) setNewStep(EMPTY_CUSTOM_STEP);
  };

  // ---------------------------------------------------------------------------
  // [HAK-03 & HAK-06] Fetch from FastAPI Backend with Fallback
  // ---------------------------------------------------------------------------
  const fetchOpportunitiesFromBackend = async () => {
    const previous = opportunityRequest.current;
    const request = { controller: new AbortController(), timeoutId: null, timedOut: false };
    opportunityRequest.current = request;
    if (previous) {
      clearTimeout(previous.timeoutId);
      previous.controller.abort();
    }
    const isCurrent = () => opportunityRequest.current === request;
    setIsLoading(true);
    setApiError(null);
    request.timeoutId = setTimeout(() => {
      request.timedOut = true;
      request.controller.abort();
    }, 3500);
    let failureKind = 'network';
    try {
      const response = await fetch('http://127.0.0.1:8000/api/opportunities', {
        signal: request.controller.signal
      });
      if (!isCurrent()) return;
      if (request.timedOut) throw new Error('timeout');
      if (!response.ok) {
        failureKind = 'http';
        throw new Error('http');
      }
      failureKind = 'invalid';
      const data = await response.json();
      if (!isCurrent()) return;
      if (request.timedOut) throw new Error('timeout');
      const items = readOpportunities(data);
      // A valid empty API list remains empty; it is not a connection failure.
      setOpportunities(items);
      setDatasetNote(Array.isArray(data) ? '' : data.dataset_note || '');
      setBackendDataSource('live-fastapi');
    } catch {
      if (!isCurrent()) return;
      const messages = {
        network: 'Could not connect to the opportunity service. Check the connection and try again.',
        timeout: 'The opportunity service took too long to respond. Please try again.',
        http: 'The opportunity service returned an unsuccessful response. Please try again later.',
        invalid: 'The opportunity service returned data that could not be used safely. Please try again later.'
      };
      setApiError(
        'Opportunity API unavailable or returned invalid data. ' +
        messages[request.timedOut ? 'timeout' : failureKind] +
        ' Using the local JSON development fallback; live opportunity updates are unavailable.'
      );
      setOpportunities(LOCAL_OPPORTUNITIES);
      setDatasetNote(localOpportunityDataset.dataset_note);
      setBackendDataSource('local-development');
    } finally {
      clearTimeout(request.timeoutId);
      if (isCurrent()) {
        opportunityRequest.current = null;
        setIsLoading(false);
      }
    }
  };

  useEffect(() => {
    fetchOpportunitiesFromBackend();
    return () => {
      const request = opportunityRequest.current;
      opportunityRequest.current = null;
      if (request) {
        clearTimeout(request.timeoutId);
        request.controller.abort();
      }
    };
  }, []);

  // ---------------------------------------------------------------------------
  // [HAK-02] Form Validation & Submission
  // ---------------------------------------------------------------------------
  const handleProfileSubmit = (e) => {
    e.preventDefault();
    const errors = {};

    if (!careerGoal.trim()) {
      errors.careerGoal = 'Please specify your Cybersecurity Career Goal.';
    }
    if (weightedAverageInvalid || (activeUserProfile.weighted_average !== null &&
        !Number.isFinite(activeUserProfile.weighted_average))) {
      errors.weighted_average = 'Enter a valid finite number, or leave weighted average blank.';
    }

    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      setProfileSubmitted(false);
      return;
    }

    setFormErrors({});
    setProfileSubmitted(true);
  };

  // ---------------------------------------------------------------------------
  // [HAK-03] Filtered Opportunities
  // ---------------------------------------------------------------------------
  const filteredOpportunities = useMemo(() => {
    return opportunities.filter((opp) => {
      const query = searchQuery.trim().toLowerCase();
      const matchesSearch = [opp.id, opp.title, opp.provider, opp.category, displayValue(opp.category),
        opp.location, displayValue(opp.study_level), opp.summary, ...(opp.skills || [])]
        .some((value) => value.toLowerCase().includes(query));
      const matchesCategory = selectedCategory === 'ALL' || opp.category === selectedCategory;

      return matchesSearch && matchesCategory;
    });
  }, [opportunities, searchQuery, selectedCategory]);

  // ---------------------------------------------------------------------------
  // [HAK-05] Pathway Management Functions
  // ---------------------------------------------------------------------------
  const generatePathwayForOpportunity = (opportunity) => {
    if (pathwayGuard.current.approved) {
      const confirmReset = window.confirm(
        'Your pathway is currently locked as "Approved by Student". Generating a new pathway will unlock and replace your current plan. Proceed?'
      );
      if (!confirmReset) return;
    }
    pathwayGuard.current.approved = false;
    const planVersion = ++pathwayGuard.current.version;
    setIsPathwayApproved(false);
    setApprovedTimestamp(null);
    resetPathwayForms();
    setSelectedOpportunityForPathway(opportunity);

    const deadline = evaluateDeadline(opportunity.deadline);
    const applicationStep = deadline.status === 'past'
      ? {
          title: `Watch for the Next Round at ${opportunity.provider}`,
          description: `This round has closed or its closing date has passed. Check ${opportunity.source_url} for provider announcements; no next opening date is assumed.`,
          timeline: 'Next-round dates: check official source'
        }
      : deadline.status === 'unknown'
        ? {
            title: `Check Application Dates with ${opportunity.provider}`,
            description: `No closing date is published. Check the official source at ${opportunity.source_url} before preparing a student-initiated application.`,
            timeline: 'Application dates to be confirmed'
          }
        : {
            title: `Check Application Availability with ${opportunity.provider}`,
            description: `Check ${opportunity.source_url} to confirm current application availability and review the published requirements. If the provider is accepting applications, any submission must be student-initiated. A deadline does not confirm eligibility.`,
            timeline: deadline.status === 'rolling' ? 'Open all year (published; check source)' : `Published closing date (${formatDate(opportunity.deadline.date)})`
          };

    // Generate editable preparation guidance without inferring eligibility gaps.
    const newMilestones = [
      {
        id: `step-${planVersion}-1`,
        phase: 'Milestone 1: Prerequisite Study & Gap Bridging',
        title: 'Review Published Requirements & Plan Foundational Study',
        description: `Review the published prerequisites and condition results for ${opportunity.title} and choose relevant study or lab work. This preparation plan does not determine eligibility.`,
        timeline: 'Weeks 1 - 4',
        status: 'pending',
        actionableUrl: ''
      },
      {
        id: `step-${planVersion}-2`,
        phase: 'Milestone 1: Prerequisite Study & Gap Bridging',
        title: 'Review Published Conditions & Confirm Required Evidence',
        description: `Review the published conditions below for ${opportunity.provider}. Prepare only evidence explicitly requested by the provider. If documentation is not specified, ask the provider what, if anything, is required.`,
        sourceConditions: opportunity.eligibility_conditions.map((condition) => ({ ...condition })),
        timeline: 'Weeks 3 - 5',
        status: 'pending',
        actionableUrl: ''
      },
      {
        id: `step-${planVersion}-3`,
        phase: 'Milestone 2: Application Submission (Student-Initiated)',
        ...applicationStep,
        status: 'pending',
        actionableUrl: opportunity.source_url
      },
      {
        id: `step-${planVersion}-4`,
        phase: 'Milestone 3: Practical Portfolio & Interview Readiness',
        title: `Technical Scenario & Interview Preparation for ${opportunity.category}`,
        description: 'Complete hands-on incident scenario walkthroughs, lab writeups, and behavioral interview practice.',
        timeline: 'Weeks 8 - 10',
        status: 'pending',
        actionableUrl: ''
      }
    ];

    setPathwayMilestones(newMilestones);

    // Scroll to pathway section
    const pathwayElement = document.getElementById('pathway-planner-section');
    if (pathwayElement) {
      pathwayElement.scrollIntoView({ behavior: 'smooth' });
    }
  };

  // Move by stable ID using current state, rather than a captured array/index.
  const moveStep = (id, direction) => {
    if (!canEditPathway()) return;
    setPathwayMilestones((prev) => {
      const index = prev.findIndex((step) => step.id === id);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= prev.length) return prev;
      const updated = [...prev];
      [updated[index], updated[target]] = [updated[target], updated[index]];
      return updated;
    });
  };

  const deleteStep = (id) => {
    if (!canEditPathway()) return;
    if (pathwayMilestones.length <= 1) {
      window.alert('Your pathway must contain at least one milestone step.');
      return;
    }
    setPathwayMilestones((prev) => prev.length > 1 ? prev.filter((step) => step.id !== id) : prev);
    if (pathwayGuard.current.editingId === id) {
      pathwayGuard.current.editingId = null;
      setEditingStepId(null);
      setEditedStepData(EMPTY_STEP_EDIT);
    }
  };

  const startEditingStep = (step) => {
    if (!canEditPathway()) return;
    pathwayGuard.current.editingId = step.id;
    setEditingStepId(step.id);
    setEditedStepData({ title: step.title, description: step.description, timeline: step.timeline });
  };

  const saveEditedStep = (id) => {
    if (!canEditPathway() || pathwayGuard.current.editingId !== id) return;
    if (!editedStepData.title.trim()) {
      window.alert('Step title cannot be empty.');
      return;
    }
    setPathwayMilestones((prev) => prev.map((step) => step.id === id ? { ...step, ...editedStepData, title: editedStepData.title.trim() } : step));
    pathwayGuard.current.editingId = null;
    setEditingStepId(null);
    setEditedStepData(EMPTY_STEP_EDIT);
  };

  const cancelEditingStep = () => {
    if (!canEditPathway()) return;
    pathwayGuard.current.editingId = null;
    setEditingStepId(null);
    setEditedStepData(EMPTY_STEP_EDIT);
  };

  const handleAddCustomStep = (e) => {
    e.preventDefault();
    if (!canEditPathway()) return;
    if (!newStep.title.trim()) {
      window.alert('Please enter a milestone title.');
      return;
    }
    const created = {
      id: `custom-step-${++pathwayGuard.current.nextCustomId}`,
      phase: newStep.phase,
      title: newStep.title.trim(),
      description: newStep.description.trim() || 'Custom student milestone step.',
      timeline: newStep.timeline.trim() || 'Flexible',
      status: 'pending',
      actionableUrl: ''
    };
    setPathwayMilestones((prev) => [...prev, created]);
    setNewStep(EMPTY_CUSTOM_STEP);
    setShowAddStepForm(false);
  };

  // [HAK-06] Student approval locks the plan, never establishes eligibility.
  const handleApprovePathway = () => {
    if (!canEditPathway()) return;
    const confirmation = window.confirm(
      'Explicit Student Approval Confirmation:\n\n' +
        'By approving this pathway, you confirm that you have reviewed and adjusted each milestone to suit your schedule.\n\n' +
        'Approval does not confirm eligibility or that applications are open.\n\n' +
        'Important Safeguard: FuturePath AU will NOT submit any applications on your behalf. You remain fully in control of direct submissions.\n\n' +
        'Lock and mark this pathway as Approved by Student?'
    );
    if (!confirmation || !canEditPathway()) return;
    pathwayGuard.current.approved = true;
    pathwayGuard.current.version += 1;
    setIsPathwayApproved(true);
    setApprovedTimestamp(new Date().toLocaleString('en-AU', { dateStyle: 'medium', timeStyle: 'short' }));
    resetPathwayForms();
  };

  const handleUnlockPathway = () => {
    if (!pathwayGuard.current.approved || pathwayGuard.current.version !== pathwayVersion) return;
    pathwayGuard.current.approved = false;
    pathwayGuard.current.version += 1;
    setIsPathwayApproved(false);
    setApprovedTimestamp(null);
  };

  // ---------------------------------------------------------------------------
  // Component Render
  // ---------------------------------------------------------------------------
  return (
    <div className="app-container">
      {/* ==================================================================== */}
      {/* HEADER & LOCKED SAFEGUARDS BANNER                                    */}
      {/* ==================================================================== */}
      <header className="app-header">
        <div className="header-top">
          <div className="logo-group">
            <span className="logo-badge">AU</span>
            <div>
              <h1 className="logo-title">FuturePath AU</h1>
              <p className="logo-subtitle">Cybersecurity Career Pathway & Opportunity Navigator</p>
            </div>
          </div>
          <div className="header-meta">
            <span className={`status-pill ${backendDataSource === 'live-fastapi' ? 'pill-live' : 'pill-mock'}`}>
              <span className="indicator-dot"></span>
              {backendDataSource === 'live-fastapi' ? 'FastAPI Connected (127.0.0.1:8000)' : 'Local JSON development fallback'}
            </span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={fetchOpportunitiesFromBackend}
              title="Refresh connection with FastAPI backend"
              disabled={isLoading}
            >
              {isLoading ? 'Checking...' : 'Check API Status'}
            </button>
          </div>
        </div>

        {/* LOCKED PROJECT CONSTRAINTS GUARANTEE BANNER */}
        <div className="safeguards-banner" role="region" aria-label="Locked Project Constraints">
          <div className="safeguards-header">
            <strong>Mandatory Project Safeguards & Ethical Governance:</strong>
          </div>
          <div className="safeguards-grid">
            <div className="safeguard-item">
              <div className="safeguard-icon-badge safeguard-icon-blue" aria-hidden="true">
                <IconLock size={18} />
              </div>
              <div>
                <strong>1. No Autonomous Applications</strong>
                <p>The platform guides and plans; it will NEVER submit job or study applications automatically.</p>
              </div>
            </div>
            <div className="safeguard-item">
              <div className="safeguard-icon-badge safeguard-icon-amber" aria-hidden="true">
                <IconScales size={18} />
              </div>
              <div>
                <strong>2. No Identity Scoring</strong>
                <p>Suitability is NEVER inferred or scored using Indigenous identity. Only published criteria are evaluated.</p>
              </div>
            </div>
            <div className="safeguard-item">
              <div className="safeguard-icon-badge safeguard-icon-teal" aria-hidden="true">
                <IconFileVerified size={18} />
              </div>
              <div>
                <strong>3. Deterministic Fact-Grounded Data</strong>
                <p>Published requirements, deadlines and source links retain their recorded verification status.</p>
              </div>
            </div>
            <div className="safeguard-item">
              <div className="safeguard-icon-badge safeguard-icon-emerald" aria-hidden="true">
                <IconUserCheck size={18} />
              </div>
              <div>
                <strong>4. Human Oversight</strong>
                <p>Students retain full agency to edit, reorder, delete, and explicitly approve their pathway.</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* ==================================================================== */}
      {/* API ERROR / FALLBACK NOTIFICATION BANNER                             */}
      {/* ==================================================================== */}
      {apiError && (
        <aside className="api-error-banner" role="alert">
          <div className="api-error-icon">
            <IconAlertTriangle size={22} />
          </div>
          <div className="api-error-body">
            <h4>Opportunity API / Development Fallback Notice</h4>
            <p>{apiError}</p>
            <div className="api-error-troubleshooting">
              <span>Quick Backend Verification:</span>
              <code>cd backend &amp;&amp; uvicorn main:app --reload --port 8000</code>
            </div>
          </div>
          <div className="api-error-actions">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={fetchOpportunitiesFromBackend}
              disabled={isLoading}
            >
              {isLoading ? 'Reconnecting...' : 'Retry Connection'}
            </button>
          </div>
        </aside>
      )}

      <main className="main-content">
        {/* ==================================================================== */}
        {/* [HAK-02] GOAL & PROFILE INPUT FORM                                  */}
        {/* ==================================================================== */}
        <section className="card section-card" id="profile-section" aria-labelledby="profile-heading">
          <div className="section-header">
            <div>
              <span className="section-step-tag">[HAK-02] Student Profile</span>
              <h2 id="profile-heading">Cybersecurity Career Goal &amp; Background Profile</h2>
            </div>
            <span role="status" className={`badge ${profileSubmitted ? 'badge-satisfied' : 'badge-draft'}`}>
              {profileSubmitted ? 'Profile inputs validated' : 'Profile draft: validation pending'}
            </span>
          </div>
          <p className="section-description">
            Define your cybersecurity aspirations and background. Only the career goal is required. Blank or not stated answers mean information is unavailable. Profile validation checks input format; eligibility evaluation belongs to the backend.
          </p>

          <form onSubmit={handleProfileSubmit} noValidate className="profile-form">
            <div className="form-grid">
              {/* Career Goal */}
              <div className="form-group">
                <label htmlFor="careerGoal" className="form-label">
                  Cybersecurity Career Goal <span className="req">*</span>
                </label>
                <input
                  id="careerGoal"
                  type="text"
                  className={`form-input ${formErrors.careerGoal ? 'input-error' : ''}`}
                  value={careerGoal}
                  onChange={(e) => { setCareerGoal(e.target.value); setProfileSubmitted(false); }}
                  required
                  placeholder="e.g., SOC Analyst, Incident Responder, Cloud Security Engineer"
                  aria-invalid={!!formErrors.careerGoal}
                  aria-describedby={formErrors.careerGoal ? 'careerGoal-error' : 'careerGoal-help'}
                />
                {formErrors.careerGoal ? (
                  <span id="careerGoal-error" className="error-message">
                    {formErrors.careerGoal}
                  </span>
                ) : (
                  <span id="careerGoal-help" className="form-help">
                    Target specialization in the Australian cyber ecosystem.
                  </span>
                )}
              </div>

              {Object.entries(PROFILE_OPTIONS).map(([field, options]) => (
                <div className="form-group" key={field}>
                  <label htmlFor={field} className="form-label">{PROFILE_LABELS[field]}</label>
                  <select id={field} name={field} className="form-input" value={profile[field]}
                    onChange={(e) => updateProfileField(field, e.target.value)}
                    aria-describedby={field === 'identity_answer' ? 'identity-help' : undefined}>
                    {options.map((option) => (
                      <option key={option} value={option}>
                        {option === 'not_stated' ? 'Not stated' : option.replaceAll('_', ' ')}
                      </option>
                    ))}
                  </select>
                  {field === 'identity_answer' && (
                    <span id="identity-help" className="form-help">Answering is voluntary. This is your own answer; identity is never inferred or scored, and identity conditions are never automatically evaluated.</span>
                  )}
                </div>
              ))}
              {['institution', 'field_of_study'].map((field) => (
                <div className="form-group" key={field}>
                  <label htmlFor={field} className="form-label">{field === 'institution' ? 'Institution' : 'Field of Study'}</label>
                  <input id={field} name={field} type="text" className="form-input" value={profile[field]}
                    placeholder={field === 'institution' ? 'e.g., Curtin University' : 'e.g., Cyber Security or Information Technology'}
                    onChange={(e) => updateProfileField(field, e.target.value)} />
                </div>
              ))}
              <div className="form-group">
                <label htmlFor="weighted_average" className="form-label">Weighted Average (optional)</label>
                <input id="weighted_average" name="weighted_average" type="number" step="any"
                  className={`form-input ${formErrors.weighted_average ? 'input-error' : ''}`}
                  value={profile.weighted_average ?? ''}
                  onChange={(e) => {
                    setWeightedAverageInvalid(e.target.validity.badInput);
                    updateProfileField('weighted_average', e.target.value === '' ? null : e.target.valueAsNumber);
                  }}
                  aria-invalid={!!formErrors.weighted_average}
                  aria-describedby="weighted-average-help weighted-average-error" />
                <span id="weighted-average-help" className="form-help">Leave blank if unavailable or you prefer not to provide it. No eligibility threshold is applied here.</span>
                <span id="weighted-average-error" className="error-message" role="alert">{formErrors.weighted_average}</span>
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="experience_notes" className="form-label">Experience Notes (optional)</label>
              <textarea id="experience_notes" name="experience_notes" rows={3} className="form-input"
                value={profile.experience_notes} onChange={(e) => updateProfileField('experience_notes', e.target.value)} />
            </div>

            <fieldset className="form-group agency-selection">
              <legend className="form-label">Preferred Agencies (optional)</legend>
              <p id="agency-help" className="form-help">Add an agency by name, then select or clear its checkbox. You can leave all agencies unselected.</p>
              <div className="form-actions">
                <label htmlFor="customAgency" className="sr-only">Agency name</label>
                <input id="customAgency" className="form-input" value={customAgency} aria-describedby="agency-help"
                  onChange={(e) => setCustomAgency(e.target.value)} placeholder="e.g., Defence" />
                <button type="button" className="btn btn-outline" disabled={!customAgency.trim()}
                  onClick={() => {
                    const agency = customAgency.trim();
                    setAgencyOptions((prev) => prev.includes(agency) ? prev : [...prev, agency]);
                    if (!profile.preferred_agencies.includes(agency)) {
                      updateProfileField('preferred_agencies', [...profile.preferred_agencies, agency]);
                    }
                    setCustomAgency('');
                  }}>Add Agency</button>
              </div>
              {agencyOptions.map((agency) => (
                <label key={agency} className="agency-option">
                  <input type="checkbox" checked={profile.preferred_agencies.includes(agency)}
                    onChange={(e) => updateProfileField('preferred_agencies', e.target.checked
                      ? [...profile.preferred_agencies, agency]
                      : profile.preferred_agencies.filter((value) => value !== agency))} />
                  {agency}
                </label>
              ))}
            </fieldset>

            {/* [HAK-02] Current Skills Dropdown Selection */}
            <div className="form-group">
              <label htmlFor="skillsDropdown" className="form-label">
                Current Skills (optional)
              </label>

              <div className="skills-dropdown-container">
                <div className="skills-selector-row">
                  <select
                    id="skillsDropdown"
                    className={`form-input skills-dropdown ${formErrors.skills ? 'input-error' : ''}`}
                    defaultValue=""
                    onChange={handleSkillSelect}
                    aria-invalid={!!formErrors.skills}
                    aria-describedby={formErrors.skills ? 'skills-error' : 'skills-help'}
                  >
                    <option value="" disabled>-- Select a cybersecurity skill to add --</option>
                    {CYBER_SKILLS_CATALOG.map((group) => (
                      <optgroup key={group.category} label={group.category}>
                        {group.skills.map((skill) => (
                          <option
                            key={skill}
                            value={skill}
                            disabled={selectedSkills.includes(skill)}
                          >
                            {skill} {selectedSkills.includes(skill) ? '✓ (Selected)' : ''}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </div>

                {formErrors.skills ? (
                  <span id="skills-error" className="error-message">
                    {formErrors.skills}
                  </span>
                ) : (
                  <span id="skills-help" className="form-help">
                    Choose skills from the categorized dropdown menu. Click &times; on any badge to remove.
                  </span>
                )}

                <label htmlFor="customSkill" className="form-label">Add Your Own Skill</label>
                <div className="form-actions">
                  <input id="customSkill" className="form-input" value={customSkill}
                    onChange={(e) => setCustomSkill(e.target.value)} placeholder="Enter a skill in your own words" />
                  <button type="button" className="btn btn-outline" disabled={!customSkill.trim()}
                    onClick={() => { addSkill(customSkill); setCustomSkill(''); }}>Add Skill</button>
                </div>
                {/* Selected Skills Tags Container */}
                <div className="skill-tags-preview" aria-label="Selected skills tags">
                  <div className="tags-header-row">
                    <span className="tags-label">Active Selected Skills ({selectedSkills.length}):</span>
                    {selectedSkills.length > 0 && (
                      <button
                        type="button"
                        className="clear-skills-link"
                        onClick={() => updateProfileField('skills', [])}
                        title="Clear all selected skills"
                      >
                        Clear All
                      </button>
                    )}
                  </div>

                  <div className="tags-pills-list">
                    {selectedSkills.length > 0 ? (
                      selectedSkills.map((skill, idx) => (
                        <span key={idx} className="skill-tag skill-tag-removable">
                          <span>{skill}</span>
                          <button
                            type="button"
                            className="skill-tag-remove-btn"
                            onClick={() => handleRemoveSkill(skill)}
                            title={`Remove ${skill}`}
                            aria-label={`Remove skill ${skill}`}
                          >
                            &times;
                          </button>
                        </span>
                      ))
                    ) : (
                      <em className="text-muted">No skills selected yet. Choose a skill from the dropdown above.</em>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="form-actions">
              <button type="submit" className="btn btn-primary">
                Validate Profile Inputs
              </button>
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => {
                  setProfile({ ...initialProfile, education_level: 'vocational', field_of_study: 'Information Technology', skills: ['networking', 'Linux', 'Wireshark'] });
                  setCareerGoal('Incident Responder / Digital Forensics');
                  setWeightedAverageInvalid(false);
                  setProfileSubmitted(false);
                  setFormErrors({});
                }}
              >
                Load Alternate Test Profile
              </button>
            </div>
          </form>
        </section>

        {/* ==================================================================== */}
        {/* [HAK-03 & HAK-04] OPPORTUNITY SEARCH & RESULTS VIEW                  */}
        {/* ==================================================================== */}
        <section className="card section-card" id="opportunities-section" aria-labelledby="opportunities-heading">
          <div className="section-header">
            <div>
              <span className="section-step-tag">[HAK-03 &amp; HAK-04] Opportunity Dataset</span>
              <h2 id="opportunities-heading">Opportunities &amp; Published Eligibility Conditions</h2>
            </div>
            <span className="results-count">
              Showing <strong>{filteredOpportunities.length}</strong> of {opportunities.length} Records
            </span>
          </div>

          <p className="section-description">
            Explore published study and career opportunities. Check each record's source and verification status. Backend eligibility outcomes are <strong>Satisfied</strong>, <strong>Unmet</strong>, or <strong>Uncertain</strong>. Until a backend result is available for your profile, prerequisites are <strong>Not yet evaluated</strong>. Missing information never means satisfied or unmet; identity conditions are never automatically evaluated.
          </p>

          <aside className="dataset-notice" role="note" aria-label="Opportunity data source">
            <strong>{backendDataSource === 'live-fastapi' ? 'Source: FastAPI opportunity API' : 'Development fallback: data/opportunities.json (bundled local copy)'}</strong>
            <p>Demo reference date: 28 November 2026 ({DEMO_REFERENCE_DATE}). Closed and past rounds remain visible for research and planning.</p>
            <p>Deadline information does not confirm that applications are currently open or that you meet eligibility requirements. Check the official source before applying.</p>
            {datasetNote && <p>{datasetNote}</p>}
          </aside>

          <aside className={`eligibility-notice ${eligibility.warning ? 'eligibility-warning' : ''}`}
            role={eligibility.warning ? 'alert' : 'status'} aria-label="Eligibility evaluation status">
            {eligibility.warning ? (
              <p>{eligibility.warning}</p>
            ) : eligibility.state === 'ready' && eligibility.results.size > 0 ? (
              <p>Validated backend condition results are shown for the current profile. They are condition outcomes, not a suitability score or an overall eligibility decision.</p>
            ) : (
              <p>Eligibility evaluation is unavailable or no backend results have been supplied. Conditions are Not yet evaluated. Published opportunity information remains available.</p>
            )}
            <p>Not yet evaluated means there is no accepted result. Uncertain is an explicit backend outcome requiring more information or review.</p>
          </aside>

          {/* Search and Filters Bar */}
          <div className="filter-bar">
            <div className="search-box">
              <label htmlFor="searchQuery" className="sr-only">
                Search opportunities
              </label>
              <input
                id="searchQuery"
                type="text"
                className="form-input search-input"
                placeholder="Search by title, provider, location, skill, or keyword..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              {searchQuery && (
                <button
                  type="button"
                  className="search-clear-btn"
                  onClick={() => setSearchQuery('')}
                  aria-label="Clear search text"
                >
                  &times;
                </button>
              )}
            </div>

            <div className="category-filters" role="group" aria-label="Filter by Category">
              {['ALL', ...OPPORTUNITY_CATEGORIES].map(
                (category) => (
                  <button
                    key={category}
                    type="button"
                    className={`filter-chip ${selectedCategory === category ? 'filter-chip-active' : ''}`}
                    onClick={() => setSelectedCategory(category)}
                    aria-pressed={selectedCategory === category}
                  >
                    {category === 'ALL' ? 'All Opportunities' : displayValue(category)}
                  </button>
                )
              )}
            </div>
          </div>

          {/* Loading UX State */}
          {isLoading && (
            <div className="state-container loading-state" role="status">
              <div className="spinner" aria-hidden="true"></div>
              <p>Fetching opportunities from FastAPI (`http://127.0.0.1:8000`)...</p>
            </div>
          )}

          {/* Empty Results UX State */}
          {!isLoading && filteredOpportunities.length === 0 && (
            <div className="state-container empty-state" role="region" aria-label="No results found">
              <div className="state-icon">
                <IconSearch size={28} />
              </div>
              <h3>No Opportunities Match Your Filter</h3>
              <p>We could not find any opportunities matching "{searchQuery}" under {selectedCategory}.</p>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setSearchQuery('');
                  setSelectedCategory('ALL');
                }}
              >
                Clear All Filters
              </button>
            </div>
          )}

          {/* Opportunity Cards Grid */}
          {!isLoading && filteredOpportunities.length > 0 && (
            <div className="opportunities-grid">
              {filteredOpportunities.map((opportunity) => {
                const deadlineEvaluation = evaluateDeadline(opportunity.deadline);
                const prereqList = opportunity.eligibility_conditions;

                // Count only validated backend outcomes; missing results stay neutral.
                const evaluatedPrereqs = prereqList.map((prereq) => ({
                  ...prereq,
                  evaluation: presentCondition(eligibility, opportunity.id, prereq)
                }));

                const counts = summarizeConditions(evaluatedPrereqs);
                const evaluatedCount = prereqList.length - counts.not_yet_evaluated;

                return (
                  <article key={opportunity.id} data-opportunity-id={opportunity.id} className="opportunity-card" aria-labelledby={`opp-title-${opportunity.id}`}>
                    {/* Card Header */}
                    <div className="card-top">
                      <div className="card-meta-line">
                        <span className="badge badge-category">{displayValue(opportunity.category)}</span>
                        <span className={`badge ${opportunity.record_type === 'synthetic' ? 'badge-uncertain' : 'badge-category'}`}>
                          {opportunity.record_type === 'synthetic' ? 'SYNTHETIC - demonstration only' : 'Real record'}
                        </span>
                        <span className={`badge ${deadlineEvaluation.badgeClass}`} title="Deterministic deadline status">
                          {deadlineEvaluation.label}
                        </span>
                      </div>
                      <h3 id={`opp-title-${opportunity.id}`} className="card-title">
                        {opportunity.title}
                      </h3>
                      <div className="provider-name">{opportunity.provider}</div>
                    </div>

                    <dl className="opportunity-facts">
                      <div><dt>Record ID</dt><dd>{opportunity.id}</dd></div>
                      <div><dt>Location</dt><dd>{opportunity.location}</dd></div>
                      <div><dt>Study level</dt><dd>{displayValue(opportunity.study_level)}</dd></div>
                    </dl>
                    <p className="card-description">{opportunity.summary}</p>
                    <div className="opportunity-skills">
                      <strong>Published skills / subjects:</strong>
                      <div className="tags-pills-list">
                        {(opportunity.skills || []).length > 0
                          ? opportunity.skills.map((skill) => <span key={skill} className="skill-tag">{skill}</span>)
                          : <span>No skills published; requirements are not assumed.</span>}
                      </div>
                    </div>
                    <div className="deadline-details">
                      <strong>{deadlineEvaluation.displayDate}</strong>
                      {opportunity.deadline.note && <p>{opportunity.deadline.note}</p>}
                    </div>

                    {/* [HAK-04] Backend condition results and published evidence */}
                    <div className="eligibility-breakdown">
                      <div className="eligibility-summary">
                        <span className="breakdown-title">Published Prerequisites &amp; Eligibility Breakdown:</span>
                        <div className="eligibility-score-pills" aria-label="Condition result counts">
                          {Object.entries(counts).filter(([, count]) => count > 0).map(([status, count]) => (
                            <span key={status} className={`summary-pill ${ELIGIBILITY_STATES[status].badgeClass}`}>
                              {count} {ELIGIBILITY_STATES[status].label}
                            </span>
                          ))}
                        </div>
                        <p className="eligibility-summary-note">
                          {evaluatedCount === 0
                            ? 'No validated backend results for this opportunity.'
                            : `${evaluatedCount} of ${prereqList.length} conditions have validated backend results. This is not an overall eligibility decision.`}
                        </p>
                      </div>

                      <ul className="prereq-list">
                        {evaluatedPrereqs.map((item) => (
                          <li key={item.id} className="prereq-item" data-condition-id={item.id}
                            data-checkable-from-profile={item.checkable_from_profile}
                            data-eligibility-status={item.evaluation.status}>
                            <div className="prereq-header">
                              <span className={`status-tag ${item.evaluation.badgeClass}`}>
                                {item.evaluation.label}
                              </span>
                              <span className="prereq-text">{item.text}</span>
                            </div>
                            <div className="prereq-audit-note">
                              <p><strong>Evidence:</strong> {item.evidence_summary}</p>
                              <p><a href={item.source_url} target="_blank" rel="noopener noreferrer">Condition source <IconExternalLink /></a></p>
                              <p>{item.type === 'identity_requirement'
                                ? 'Voluntary student confirmation only; identity is never automatically evaluated or scored.'
                                : item.checkable_from_profile
                                  ? 'Marked checkable from profile in the source data; decisions belong to the backend.'
                                  : 'Requires human review; not checkable from profile.'}</p>
                              <p><strong>Status:</strong> {item.evaluation.reason}</p>
                              {item.evaluation.backendExplanation && (
                                <p><strong>Backend explanation:</strong> {item.evaluation.backendExplanation}</p>
                              )}
                            </div>
                          </li>
                        ))}
                      </ul>
                    </div>

                    {/* Published source and recorded verification metadata */}
                    <div className="verification-footer">
                      <div className="verification-details">
                        <span className="verified-date">
                          {opportunity.record_type === 'synthetic' ? 'Synthetic record date' : 'Last checked / imported'}: <strong>{opportunity.verification.verified_on}</strong>
                        </span>
                        <span className="source-link-container">
                          Official Source:&nbsp;
                          <a
                            href={opportunity.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="official-url"
                            title={`Open official ${opportunity.provider} portal`}
                          >
                            Visit Portal <IconExternalLink size={13} />
                          </a>
                        </span>
                      </div>

                      <div className="verification-method">
                        <strong>Verification: {displayValue(opportunity.verification.status)}</strong>
                        <p>{opportunity.verification.method}</p>
                      </div>
                      {opportunity.data_notes && (
                        <details className="data-notes">
                          <summary>Source and data notes</summary>
                          <p>{opportunity.data_notes}</p>
                        </details>
                      )}

                      {/* Action to Generate / Populate Pathway */}
                      <div className="card-action-bar">
                        <button
                          type="button"
                          className="btn btn-primary btn-sm"
                          onClick={() => generatePathwayForOpportunity(opportunity)}
                          title="Generate a student-guided sequential milestone pathway for this opportunity"
                        >
                          Plan Pathway for this Opportunity &rarr;
                        </button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>

        {/* ==================================================================== */}
        {/* [HAK-05] EDITABLE PATHWAY & STUDENT APPROVAL                         */}
        {/* ==================================================================== */}
        <section
          className={`card section-card pathway-container ${isPathwayApproved ? 'pathway-locked' : 'pathway-draft'}`}
          id="pathway-planner-section"
          aria-labelledby="pathway-heading"
        >
          <div className="section-header">
            <div>
              <span className="section-step-tag">[HAK-06] Human Oversight &amp; Agency</span>
              <h2 id="pathway-heading">Student Career Pathway Planner</h2>
            </div>
            {isPathwayApproved ? (
              <div className="approval-status-badge">
                <IconCheckCircle size={22} className="approved-icon" />
                <div>
                  <strong>Approved by Student</strong>
                  <div className="approval-time">Locked on: {approvedTimestamp}</div>
                </div>
              </div>
            ) : (
              <span className="badge badge-draft">Draft Plan (Editable by Student)</span>
            )}
          </div>

          <p className="form-help pathway-approval-note">Student approval confirms your plan choices only. It does not establish eligibility, confirm application availability or submit any applications.</p>

          {/* Locked vs Draft Informational Alert */}
          {isPathwayApproved ? (
            <div className="pathway-banner banner-approved" role="status">
              <span className="banner-icon" aria-hidden="true">
                <IconLock size={18} />
              </span>
              <div>
                <strong>Plan Locked &amp; Approved by Student.</strong>
                <p>
                  This career roadmap has been finalized with your explicit consent. Editing and reordering are frozen to preserve your deliberate sequence. You can unlock and revise the plan at any time.
                </p>
              </div>
              <button
                type="button"
                className="btn btn-outline btn-sm"
                onClick={handleUnlockPathway}
                title="Unlock pathway to make adjustments"
              >
                Unlock &amp; Revise Plan
              </button>
            </div>
          ) : (
            <div className="pathway-banner banner-guidance" role="region">
              <span className="banner-icon" aria-hidden="true">
                <IconCompass size={18} />
              </span>
              <div>
                <strong>Active Human Oversight:</strong>
                <p>
                  You have full authority to reorder milestones, customize step text, remove unneeded actions, or add personal study targets. Once satisfied, click <strong>"Approve Pathway"</strong> to finalize your official plan.
                </p>
              </div>
            </div>
          )}

          {/* Current Target Opportunity Reference */}
          {selectedOpportunityForPathway && (
            <div className="pathway-target-banner">
              <span>Tailored Roadmap for:</span>
              <strong> {selectedOpportunityForPathway.title}</strong>
              <span className="target-provider">({selectedOpportunityForPathway.provider})</span>
            </div>
          )}

          {/* Milestones Sequential List */}
          <div className="milestones-timeline" role="list">
            {pathwayMilestones.map((step, index) => {
              const isEditing = editingStepId === step.id;

              return (
                <div
                  key={step.id}
                  className={`milestone-item ${isEditing ? 'milestone-editing' : ''}`}
                  role="listitem"
                >
                  <div className="milestone-number-col">
                    <div className="milestone-badge">{index + 1}</div>
                    {index < pathwayMilestones.length - 1 && <div className="milestone-connector"></div>}
                  </div>

                  <div className="milestone-content">
                    {/* Header info */}
                    <div className="milestone-phase-row">
                      <span className="milestone-phase-label">{step.phase}</span>
                      <span className="milestone-timeline-badge">{step.timeline}</span>
                    </div>

                    {/* Step Body: Normal View or In-Place Edit Mode */}
                    {isEditing ? (
                      <div className="milestone-edit-form">
                        <div className="form-group">
                          <label className="form-label" htmlFor={`edit-title-${step.id}`}>
                            Milestone Title:
                          </label>
                          <input
                            id={`edit-title-${step.id}`}
                            type="text"
                            className="form-input"
                            value={editedStepData.title}
                            onChange={(e) => updateEditedStep('title', e.target.value)}
                          />
                        </div>
                        <div className="form-group">
                          <label className="form-label" htmlFor={`edit-desc-${step.id}`}>
                            Actionable Details &amp; Guidance:
                          </label>
                          <textarea
                            id={`edit-desc-${step.id}`}
                            rows={3}
                            className="form-input"
                            value={editedStepData.description}
                            onChange={(e) =>
                              updateEditedStep('description', e.target.value)
                            }
                          />
                        </div>
                        <div className="form-group">
                          <label className="form-label" htmlFor={`edit-timeline-${step.id}`}>
                            Target Timeline:
                          </label>
                          <input
                            id={`edit-timeline-${step.id}`}
                            type="text"
                            className="form-input"
                            value={editedStepData.timeline}
                            onChange={(e) =>
                              updateEditedStep('timeline', e.target.value)
                            }
                          />
                        </div>
                        <div className="edit-btn-group">
                          <button
                            type="button"
                            className="btn btn-primary btn-sm"
                            onClick={() => saveEditedStep(step.id)}
                          >
                            Save Step Changes
                          </button>
                          <button
                            type="button"
                            className="btn btn-outline btn-sm"
                            onClick={cancelEditingStep}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <h4 className="milestone-title">{step.title}</h4>
                        <p className="milestone-desc">{step.description}</p>
                        {step.sourceConditions && (
                          <details className="pathway-evidence">
                            <summary>Published conditions and evidence sources</summary>
                            <ul>
                              {step.sourceConditions.map((condition) => (
                                <li key={condition.id}>
                                  <p>{condition.text}</p>
                                  <p><strong>Evidence:</strong> {condition.evidence_summary}</p>
                                  <a href={condition.source_url} target="_blank" rel="noopener noreferrer">Official condition source <IconExternalLink /></a>
                                </li>
                              ))}
                            </ul>
                          </details>
                        )}
                        {step.actionableUrl && (
                          <div className="milestone-action-link">
                            <span className="safeguard-badge-inline">Mandatory Safeguard: Student Direct Submission</span>
                            <a
                              href={step.actionableUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="official-url"
                            >
                              View Official Source &#x2197;
                            </a>
                          </div>
                        )}
                      </>
                    )}

                    {/* Step Controls (Reorder, Edit, Delete) - Only available in Draft Mode */}
                    {!isPathwayApproved && !isEditing && (
                      <div className="milestone-controls">
                        <button
                          type="button"
                          className="control-btn"
                          onClick={() => moveStep(step.id, -1)}
                          disabled={index === 0}
                          title="Move step earlier in sequence"
                          aria-label={`Move step ${index + 1} up`}
                        >
                          &uarr; Move Up
                        </button>
                        <button
                          type="button"
                          className="control-btn"
                          onClick={() => moveStep(step.id, 1)}
                          disabled={index === pathwayMilestones.length - 1}
                          title="Move step later in sequence"
                          aria-label={`Move step ${index + 1} down`}
                        >
                          &darr; Move Down
                        </button>
                        <button
                          type="button"
                          className="control-btn"
                          onClick={() => startEditingStep(step)}
                          title="Edit this step text in-place"
                          aria-label={`Edit step ${index + 1}`}
                        >
                          &#x270E; Edit
                        </button>
                        <button
                          type="button"
                          className="control-btn control-btn-delete"
                          onClick={() => deleteStep(step.id)}
                          title="Remove this milestone"
                          aria-label={`Delete step ${index + 1}`}
                        >
                          &times; Delete
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Add Custom Step Form / Toggle */}
          {!isPathwayApproved && (
            <div className="add-step-area">
              {!showAddStepForm ? (
                <button
                  type="button"
                  className="btn btn-outline btn-sm"
                  onClick={() => toggleCustomStepForm(true)}
                >
                  + Add Custom Milestone Step
                </button>
              ) : (
                <form onSubmit={handleAddCustomStep} className="add-step-card">
                  <h4>Add Custom Milestone Step</h4>
                  <div className="form-grid">
                    <div className="form-group">
                      <label className="form-label" htmlFor="new-step-phase">
                        Milestone Phase
                      </label>
                      <select
                        id="new-step-phase"
                        className="form-input"
                        value={newStep.phase}
                        onChange={(e) => updateCustomStep('phase', e.target.value)}
                      >
                        <option value="Milestone 1: Prerequisite Study & Bridging">Milestone 1: Prerequisite Study</option>
                        <option value="Milestone 2: Application Preparation">Milestone 2: Application Preparation</option>
                        <option value="Milestone 3: Practical Portfolio & Lab">Milestone 3: Practical Portfolio</option>
                        <option value="Milestone 4: Interview & Offer Stage">Milestone 4: Interview &amp; Offer</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label" htmlFor="new-step-timeline">
                        Target Timeline
                      </label>
                      <input
                        id="new-step-timeline"
                        type="text"
                        className="form-input"
                        value={newStep.timeline}
                        onChange={(e) => updateCustomStep('timeline', e.target.value)}
                        placeholder="e.g., Weeks 5 - 7"
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label" htmlFor="new-step-title">
                      Milestone Title <span className="req">*</span>
                    </label>
                    <input
                      id="new-step-title"
                      type="text"
                      className="form-input"
                      value={newStep.title}
                      onChange={(e) => updateCustomStep('title', e.target.value)}
                      placeholder="e.g., Complete TryHackMe Pre-Security &amp; Blue Team Track"
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label" htmlFor="new-step-desc">
                      Detailed Instructions / Action Notes
                    </label>
                    <textarea
                      id="new-step-desc"
                      rows={2}
                      className="form-input"
                      value={newStep.description}
                      onChange={(e) => updateCustomStep('description', e.target.value)}
                      placeholder="Detail specific tasks, labs, or documentation needed."
                    />
                  </div>

                  <div className="form-actions">
                    <button type="submit" className="btn btn-primary btn-sm">
                      Insert Into Pathway
                    </button>
                    <button
                      type="button"
                      className="btn btn-outline btn-sm"
                      onClick={() => toggleCustomStepForm(false)}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}

          {/* Pathway Approval Call-to-Action Bar */}
          <div className="pathway-footer-actions">
            {!isPathwayApproved ? (
              <div className="approval-cta-box">
                <div>
                  <h4>Ready to Finalize Your Roadmap?</h4>
                  <p>
                    Review your milestone sequence. Once you click <strong>"Approve Pathway"</strong>, the plan is locked under your student signature.
                  </p>
                </div>
                <button
                  type="button"
                  className="btn btn-success btn-lg"
                  onClick={handleApprovePathway}
                >
                  &#x2714; Approve Pathway
                </button>
              </div>
            ) : (
              <div className="approved-summary-bar">
                <div className="approved-meta">
                  <span className="stamp-badge">STUDENT APPROVED</span>
                  <span>Plan choices approved by student on {approvedTimestamp}</span>
                </div>
                <button
                  type="button"
                  className="btn btn-outline btn-sm"
                  onClick={() => window.print()}
                  title="Print or export your approved pathway plan"
                >
                  <IconPrinter size={15} /> Print / Export Pathway
                </button>
              </div>
            )}
          </div>
        </section>
      </main>

      {/* ==================================================================== */}
      {/* ACCESSIBLE FOOTER WITH ETHICAL GOVERNANCE STATEMENT                  */}
      {/* ==================================================================== */}
      <footer className="app-footer">
        <div className="footer-content">
          <p>
            <strong>FuturePath AU</strong> &mdash; Built in strict compliance with the University Assessment Brief and Team Workplan (Member: Hakm).
          </p>
          <p className="footer-disclaimer">
            Safeguards strictly enforced: No autonomous submissions &bull; No identity scoring &bull; Deterministic source data &bull; Mandatory human student oversight.
          </p>
        </div>
      </footer>
    </div>
  );
}
