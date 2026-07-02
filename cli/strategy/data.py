"""Strategy mindmap data — ported from strategy_mindmap.html."""

from __future__ import annotations

# ════════════════════════════════════════════
# STATUS & PRIORITY CONFIG
# ════════════════════════════════════════════

STATUS_CONFIG = {
    "active": {"label": "Active", "color": "#238551", "bg": "rgba(35,133,81,0.2)"},
    "planned": {"label": "Planned", "color": "#2D72D2", "bg": "rgba(45,114,210,0.2)"},
    "pending": {"label": "Pending", "color": "#C87619", "bg": "rgba(200,118,25,0.2)"},
    "completed": {"label": "Done", "color": "#5F6B7C", "bg": "rgba(95,107,124,0.2)"},
    "at-risk": {"label": "At Risk", "color": "#CD4246", "bg": "rgba(205,66,70,0.2)"},
}

PRIORITY_CONFIG = {
    "critical": {"label": "Critical", "color": "#CD4246"},
    "high": {"label": "High", "color": "#C87619"},
    "medium": {"label": "Medium", "color": "#2D72D2"},
    "low": {"label": "Low", "color": "#5F6B7C"},
}

# ════════════════════════════════════════════
# NODE DATA (entity enrichment)
# ════════════════════════════════════════════

NODE_DATA: dict[str, dict] = {
    "ericsson": {
        "status": "active", "priority": "critical", "phase": "recon", "deadline": None,
        "properties": {"Role": "Strategy Hub", "GPA": "3.50", "Votes": "266 (4th/38)", "Supporters": "300+", "UTMSU Slate": "VP Internal (uncertain — Mekayel lost BOD seat)"},
        "actions": ["Confirm CS POSt declaration with registrar", "Email mcss@utmsu.ca", "Join UTMIST Discord", "Consider VP Internal role on Mekayel's UTMSU slate (2027-28)"],
    },
    "pyko": {
        "status": "active", "priority": "critical", "phase": "recon", "deadline": None,
        "properties": {"Type": "EdTech Startup", "Raised": "$150K", "Valuation": "$10M CAD", "Team": "12 members", "Time": "15-20 hrs/week", "Parent Entity": "Pyko Lab (nonprofit)"},
        "actions": ["Apply to ICUBE Venture Forward", "Submit to MISTic R&D", "Recruit ML talent from UTMIST", "Formalize Pyko Lab governance (golden share)"],
    },
    "mcss": {
        "status": "active", "priority": "critical", "phase": "recon", "deadline": "2027-02-28",
        "properties": {"Type": "Academic Society", "Members": "1,500+", "Event": "DeerHacks", "Election": "Feb 2027"},
        "actions": ["Email mcss@utmsu.ca for constitution", "Apply for director/associate role Jul-Aug", "Attend every event Sep-Dec 2026", "Lock slate by Jan 2027", "Campaign + WIN by end of Feb 2027"],
    },
    "council": {
        "status": "pending", "priority": "high", "phase": "recon", "deadline": "2026-04-10",
        "properties": {"Type": "Governance", "CC Seats": "3/14 candidates", "AA Seats": "5/11 candidates", "Time": "10-15 hrs/YEAR"},
        "actions": ["Wait for Apr 10 results", "If elected attend all meetings"],
    },
    "utmist": {
        "status": "planned", "priority": "high", "phase": "recon", "deadline": "2026-09-01",
        "properties": {"Type": "AI/ML Org", "Community": "2,700+", "Devs": "70+", "Sponsors": "AMD, Google, Qualcomm"},
        "actions": ["Join UTMIST Discord NOW", "Start contributing to Mist platform (40 issues)", "Apply Sep 2026 for FYR + ML Dev"],
    },
    "pyko_club": {
        "status": "planned", "priority": "high", "phase": "recon", "deadline": "2026-07-31",
        "properties": {"Type": "Campus Club", "Name": "Pyko Learning Society", "Status": "Preparing application", "Window": "May 1 - Jul 31", "Members": "30 target"},
        "actions": ["Transition Ericsson to Founding Researcher at Pyko Lab", "Revise constitution for Pyko Learning Society", "Recruit 30 UTM undergrad members", "Draft proactive disclosure statement", "Attend UTMSU recognition training (May-Jul)", "Submit SOP + UTMSU applications", "Open club bank account"],
    },
    "pyko_lab": {
        "status": "planned", "priority": "high", "phase": "recon", "deadline": None,
        "properties": {"Type": "Nonprofit", "Role": "Parent Entity", "Controls": "Pyko Canada Ltd.", "Mechanism": "Golden share / board appointment"},
        "actions": ["Incorporate as nonprofit", "Establish independent board", "Transition Ericsson from Director to Founding Researcher", "Formalize governance mechanism over Pyko Canada Ltd."],
    },
    "ambassador_program": {
        "status": "planned", "priority": "medium", "phase": "insider", "deadline": None,
        "properties": {"Type": "Startup Ops", "Lead": "Mekayel Omier", "Funded By": "Pyko Canada Ltd."},
        "actions": ["Formalize ambassador role for Mekayel", "Begin club sponsorship outreach (Sep 2026)", "Recruit additional ambassadors"],
    },
    "mcss_election": {
        "status": "planned", "priority": "critical", "phase": "win", "deadline": "2027-02-28",
        "properties": {"Type": "Election", "Platform": "SimplyVoting (confirmed)", "Electorate": "1,500-2,500", "2026-27 Result": "Emily Su elected President unopposed"},
        "actions": ["Form complete slate by Jan 2027", "Commission campaign website from Ethan", "Assess whether Emily Su will seek re-election by Nov 2026"],
    },
    "mcss_slate": {
        "status": "planned", "priority": "critical", "phase": "expansion", "deadline": "2027-01-31",
        "properties": {"Type": "Campaign Team", "Size": "5 positions", "Gender Target": "3F/2M"},
        "actions": ["Scout candidates Sep-Nov 2026", "Coffee chats Dec 2026", "Lock slate Jan 2027"],
    },
    "vector": {
        "status": "planned", "priority": "medium", "phase": "future", "deadline": "2028-02-01",
        "properties": {"Type": "Research Lab", "Pay": "$15.81/hr", "Duration": "16-32 weeks"},
        "actions": ["Complete CSC311 + CSC413", "Build ML project portfolio", "Apply Feb 2028"],
    },
    "mekayel": {
        "status": "at-risk", "priority": "medium", "phase": "recon", "deadline": None,
        "properties": {
            "Role": "UTMSU Division I Director (outgoing) + Pyko Ambassador",
            "Status": "Won Div I first-year rep (Fall 2025 by-election). Lost Div II re-election (375 votes, 20th/23, cutoff ~538).",
            "BOD Term": "Div I term ending when new board seated (Apr/May 2026).",
            "UTMSU Goal": "President 2027-28 (significantly reduced confidence)",
            "Path Status": "Disrupted — lost Div II race badly.",
            "Ambassador": "Leads Pyko startup campus ops",
            "Bridge Contact": "Maryam Zeeshan served with him on Div I, now top Div II vote-getter (681)",
        },
        "actions": [
            "Lead campus ambassador program for Pyko Canada Ltd.",
            "Use remaining Div I term to introduce Ericsson to UTMSU contacts before term ends",
            "Leverage connection to Maryam Zeeshan (served together on Div I, now new BOD member)",
            "Reassess UTMSU presidential viability — 375 votes vs 538 cutoff is a significant gap",
        ],
    },
    "courses": {
        "status": "active", "priority": "critical", "phase": "recon", "deadline": None,
        "properties": {"cGPA": "3.50", "Target": "3.70", "Path": "CS Specialist + PHL Minor + Math Minor"},
        "actions": ["Confirm POSt declaration", "Register for CSC207 Summer 2026"],
    },
    "risks": {
        "status": "active", "priority": "high", "phase": "recon", "deadline": None,
        "properties": {"Fatal": "1 (POSt)", "High": "2 (Burnout, Incumbent)", "Medium": "2 (Seats, CRO)", "Low": "1 (Pyko)"},
        "actions": ["Confirm POSt THIS WEEK", "Emily Su confirmed as President — assess re-election likelihood", "Build relationship with incoming 2026-27 exec"],
    },
    "keydates": {
        "status": "active", "priority": "critical", "phase": "recon", "deadline": None,
        "properties": {"Next": "Apr 10 (Governance results)", "Window": "May-Jul (SOP)", "Election": "Feb 2027"},
        "actions": [],
    },
    "phase1": {
        "status": "active", "priority": "critical", "phase": "recon", "deadline": None,
        "properties": {"Period": "Mar-Apr 2026", "Effort": "~1 hour + waiting"},
        "actions": ["Email MCSS", "Join UTMIST Discord", "Submit Pyko to MISTic R&D", "Email ICUBE"],
    },
    "competitors": {
        "status": "active", "priority": "high", "phase": "recon", "deadline": None,
        "properties": {"Top Threat": "Emily Su (Incoming President 2026-27)", "Pattern": "Incumbent advantage confirmed"},
        "actions": ["Emily Su confirmed as 2026-27 President — assess re-election likelihood", "Prepare differentiation strategy against incumbent", "Study 2026-27 exec for internal dynamics and potential allies"],
    },
    "raaid": {
        "status": "active", "priority": "medium", "phase": "recon", "deadline": None,
        "properties": {"Role": "UTMAC Member + Mekayel Ally", "Program": "BSc Co-op CS/Math/Stats (2025-2029)", "Skills": "Soccer coaching, event planning, leadership"},
        "actions": ["Connect through Mekayel", "Join UTMAC council together"],
    },
    "utmac": {
        "status": "planned", "priority": "medium", "phase": "recon", "deadline": None,
        "properties": {"Type": "Athletic Council", "Purpose": "Student-athlete advocacy, varsity programs", "Role": "Council member (not exec)"},
        "actions": ["Join UTMAC as council member", "Coordinate with Raaid Shabeer on athletics advocacy"],
    },
    "vpcl_opportunity": {
        "status": "planned", "priority": "medium", "phase": "insider", "deadline": "2026-05-31",
        "properties": {"Type": "Appointed Position", "Appointed By": "UTMSU Board of Directors", "Scope": "6th UTMSU executive — chairs Clubs Committee", "Pay": "Full-time paid position"},
        "actions": ["Monitor utmsu.ca/employment/ starting April 2026 for VP CL posting", "Have Mekayel introduce Ericsson to outgoing VP CL before term ends", "Even if not applying: influence who fills this seat through BOD contacts"],
    },
    "utmsu_committees": {
        "status": "planned", "priority": "medium", "phase": "insider", "deadline": "2026-06-30",
        "properties": {"Type": "Committee Appointments", "Committees": "Elections & Referenda, Policy & Procedure, Bursary, CIJC", "Appointed By": "New UTMSU Board of Directors (seated Apr/May 2026)", "Key Target": "Elections & Referenda Committee"},
        "actions": ["Ask Mekayel to flag committee openings when new Board starts meeting (May 2026)", "Target Elections & Referenda Committee — directly relevant to Feb 2027 MCSS election", "Build relationship with new BOD members who control appointments"],
    },
    "workstudy": {
        "status": "planned", "priority": "high", "phase": "recon", "deadline": "2026-03-30",
        "properties": {"Type": "Paid Position", "Pay": "$17.20+/hr", "Portal": "CLNx (clnx.utoronto.ca)", "Requirement": "0.5 FCE enrollment (CSC207 Summer qualifies)", "Strategic Value": "Departmental embedding", "Target Depts": "MCS Department, Dean's Office, Student Affairs"},
        "actions": ["Apply March 30 on Day 1 via CLNx", "Filter for MCS department, Dean's Office, or Student Affairs positions", "Also apply to Residence Work-Study (opens Apr 6, deadline Apr 30)", "Prioritize positions that build faculty/admin relationships"],
    },
    "campus_affairs": {
        "status": "planned", "priority": "medium", "phase": "insider", "deadline": None,
        "properties": {"Type": "Governance Committee", "Members": "34 total (6 undergrad seats)", "Chair": "Robert Gerlai", "Scope": "Non-academic student life policy — budget, campus services, student societies, security", "Meeting Schedule": "5 times/year Sep-Apr"},
        "actions": ["Contact Cindy Ferencz (cindy.ferencz@utoronto.ca) about appointed positions", "If elected to Campus Council (Apr 10), the appointed CAC seat becomes accessible", "Watch for by-elections if vacancies arise"],
    },
    "orientation": {
        "status": "planned", "priority": "medium", "phase": "insider", "deadline": "2026-07-15",
        "properties": {"Type": "Volunteer Role", "Role": "Pathfinder — guides new students during orientation", "Voter Value": "Direct high-visibility contact with incoming first-years (largest MCSS voter bloc)", "Time": "~1 week during September orientation"},
        "actions": ["Watch utm.utoronto.ca/orientation/orientation-volunteering for application opening", "Apply as Pathfinder — voter-facing visibility play for MCSS Feb 2027"],
    },
}

# ════════════════════════════════════════════
# PHASES
# ════════════════════════════════════════════

PHASES = [
    {"id": "recon", "name": "Reconnaissance", "code": "RECON", "start": "2026-03-17", "end": "2026-04-30"},
    {"id": "insider", "name": "Insider Positioning", "code": "INSIDER", "start": "2026-05-01", "end": "2026-08-31"},
    {"id": "expansion", "name": "Expansion", "code": "EXPAND", "start": "2026-09-01", "end": "2026-12-31"},
    {"id": "slate", "name": "Slate Formation + Win", "code": "WIN", "start": "2027-01-01", "end": "2027-02-28"},
]

# ════════════════════════════════════════════
# DOMAINS
# ════════════════════════════════════════════

DOMAINS = {
    "all": {"label": "All Domains", "color": "#00D4FF", "icon": "\u2B21"},
    "startup": {"label": "Startup", "color": "#a855f7", "icon": "\u25B2"},
    "mcss": {"label": "MCSS Campaign", "color": "#3b82f6", "icon": "\u25A0"},
    "governance": {"label": "Governance", "color": "#10b981", "icon": "\u25C6"},
    "ai_ml": {"label": "AI/ML Career", "color": "#f97316", "icon": "\u25CF"},
    "academic": {"label": "Academic", "color": "#06b6d4", "icon": "\u25C7"},
}

# ════════════════════════════════════════════
# ENTITY TYPES
# ════════════════════════════════════════════

ENTITY_TYPES = {
    "position": {"label": "Position", "icon": "\u25C6"},
    "organization": {"label": "Organization", "icon": "\u25A0"},
    "person": {"label": "Person", "icon": "\u25CF"},
    "event": {"label": "Event", "icon": "\u25B2"},
    "resource": {"label": "Resource", "icon": "\u25C7"},
    "milestone": {"label": "Milestone", "icon": "\u25C8"},
    "goal": {"label": "Goal", "icon": "\u2605"},
    "voter_bloc": {"label": "Voter Bloc", "icon": "\u25CE"},
}

ENTITY_TYPE_MAP: dict[str, str] = {
    "ericsson": "position", "pyko": "position", "mcss": "position", "council": "position",
    "utmist": "position", "pyko_club": "position", "pyko_lab": "organization", "ambassador_program": "organization",
    "mcss_election": "event", "mcss_slate": "organization",
    "vp_internal": "position", "vp_finance": "position", "vp_external": "position", "vp_marketing": "position",
    "wisc": "organization", "mathclub": "organization", "cssc": "organization", "dsc": "organization",
    "utmsam": "organization", "mcsdept": "organization", "utmadmin": "organization", "utmsu": "organization", "utmac": "organization",
    "vpcl_opportunity": "position", "utmsu_committees": "position", "workstudy": "resource", "campus_affairs": "position", "orientation": "event",
    "vp_campuslife": "person", "mekayel": "person", "ethan": "person", "raaid": "person",
    "saurabh": "person", "henrik": "person", "faculty": "person",
    "icube": "resource", "mistic": "resource", "eigenai": "event", "genai": "event",
    "deerhacks": "event", "vector": "goal", "courses": "resource", "risks": "resource",
    "keydates": "milestone", "phase1": "milestone", "phase2": "milestone", "phase3": "milestone", "phase4": "milestone",
    "firstyears": "voter_bloc", "cs_students": "voter_bloc", "math_students": "voter_bloc",
    "discord": "voter_bloc", "voting_platform": "resource", "hacklab": "resource",
    "competitors": "person",
}

ENTITY_DOMAINS: dict[str, list[str]] = {
    "ericsson": ["startup", "mcss", "governance", "ai_ml", "academic"],
    "pyko": ["startup"], "pyko_club": ["startup"], "pyko_lab": ["startup"], "ambassador_program": ["startup"], "icube": ["startup"], "mistic": ["startup", "ai_ml"],
    "ethan": ["startup"],
    "mcss": ["mcss"], "mcss_election": ["mcss"], "mcss_slate": ["mcss"], "vp_internal": ["mcss"],
    "vp_finance": ["mcss"], "vp_external": ["mcss"], "vp_marketing": ["mcss"], "deerhacks": ["mcss"],
    "wisc": ["mcss"], "mathclub": ["mcss"], "cssc": ["mcss"], "dsc": ["mcss"], "utmsam": ["mcss"],
    "competitors": ["mcss"],
    "council": ["governance"], "utmsu": ["governance"], "utmadmin": ["governance"],
    "vp_campuslife": ["governance"], "mekayel": ["governance", "startup"],
    "mcsdept": ["governance", "academic"],
    "utmist": ["ai_ml"], "eigenai": ["ai_ml"], "genai": ["ai_ml"], "vector": ["ai_ml", "academic"],
    "courses": ["academic"], "risks": ["mcss", "governance"], "keydates": ["mcss", "governance"],
    "phase1": ["mcss"], "phase2": ["mcss"], "phase3": ["mcss"], "phase4": ["mcss"],
    "firstyears": ["mcss"], "cs_students": ["mcss", "ai_ml"], "math_students": ["mcss"],
    "faculty": ["academic", "governance"],
    "raaid": ["governance"],
    "utmac": ["governance"],
    "vpcl_opportunity": ["governance"], "utmsu_committees": ["governance"], "workstudy": ["academic", "governance"], "campus_affairs": ["governance"], "orientation": ["mcss"],
    "saurabh": ["mcss"], "henrik": ["mcss"],
    "discord": ["mcss"], "voting_platform": ["mcss"], "hacklab": ["mcss"],
}

# ════════════════════════════════════════════
# THEORY OF VICTORY
# ════════════════════════════════════════════

THEORY_OF_VICTORY = {
    "statement": (
        "Win MCSS presidency by offering a compelling alternative to the incumbent. "
        "Combine technical credibility (Pyko startup, UTMIST ML), governance experience "
        "(Campus Council/AA), Math/Stats representation (VP Finance vacancy proves the gap), "
        "and community presence (every MCSS event Sep-Dec 2026). Against an incumbent, "
        '"more of the same" loses \u2014 Ericsson must represent visible, specific improvement.'
    ),
    "vote_math": {
        "needed": 400,
        "turnout": "800-1200",
        "cs_students": 250,
        "first_year": 100,
        "math_stats": 50,
        "slate_network": 100,
    },
    "pillars": [
        {"title": "Builder Credibility", "text": "No other candidate has built a funded product. Pyko ($150K raised, 12-person team) is proof of execution, not just promises."},
        {"title": "Institutional Access", "text": "Campus Council + AA seat gives policy insight no other MCSS candidate has. Bring governance knowledge to society leadership."},
        {"title": "Community First", "text": "Attend every MCSS event Sep-Dec 2026. Be known as someone who shows up before asking for votes. DeerHacks involvement as credibility anchor."},
    ],
    "messaging_by_bloc": {
        "cs_students": "I built Pyko \u2014 I understand what CS students need because I am one building real software.",
        "first_year": "I'll make MCSS the first place you go for career help, not the last. More workshops, more mentorship, more hackathons.",
        "math_stats": "Math and stats students are MCS students too. My slate includes a Math rep because you deserve a voice.",
    },
}

# ════════════════════════════════════════════
# TIME BUDGET (Weekly Hours)
# ════════════════════════════════════════════

TIME_BUDGET = {
    "available": 112,  # 16 hrs/day x 7
    "items": [
        {"label": "Classes + Study", "hours": 35, "color": "#06b6d4", "phase": "all"},
        {"label": "Pyko Startup", "hours": 17, "color": "#a855f7", "phase": "all"},
        {"label": "MCSS Prep", "hours": 5, "color": "#3b82f6", "phase": "recon"},
        {"label": "Governance", "hours": 2, "color": "#10b981", "phase": "all"},
        {"label": "UTMIST", "hours": 3, "color": "#f97316", "phase": "recon"},
        {"label": "Sleep", "hours": 49, "color": "#404854", "phase": "all", "fixed": True},
        {"label": "Meals + Transit", "hours": 14, "color": "#383E47", "phase": "all", "fixed": True},
        {"label": "Exercise + Social", "hours": 7, "color": "#5F6B7C", "phase": "all", "fixed": True},
    ],
}

# ════════════════════════════════════════════
# DECISION RULES
# ════════════════════════════════════════════

DECISION_RULES = [
    {"condition": "GPA-threatening deadline conflicts with anything", "result": "GPA wins. Always. POSt and Vector depend on it. No exceptions.", "priority": "absolute"},
    {"condition": "MCSS campaign event conflicts with Pyko work (Phase 3-4)", "result": "MCSS wins during election season (Jan-Feb 2027). Pyko can survive 8 weeks of reduced attention.", "priority": "high"},
    {"condition": "Pyko investor/funding deadline conflicts with campus activities", "result": "Pyko wins. $150K raised means fiduciary obligations exist. Campus roles are voluntary.", "priority": "high"},
    {"condition": "Mekayel UTMSU campaign needs resources during MCSS campaign", "result": "MCSS is primary. Support Mekayel passively. Do not let his campaign consume your bandwidth.", "priority": "medium"},
    {"condition": "UTMAC or UTMIST event conflicts with MCSS or Pyko", "result": "UTMAC and UTMIST are deferrable at any time. They are nice-to-have, not must-have.", "priority": "low"},
    {"condition": "Two MCSS events on same day as Pyko sprint", "result": "Attend the MCSS event with more voter-facing exposure. Skip internal Pyko meetings \u2014 delegate to Ethan.", "priority": "medium"},
]

# ════════════════════════════════════════════
# CONTINGENCY PLANS
# ════════════════════════════════════════════

CONTINGENCIES = [
    {"goal": "MCSS President", "fallback": "If defeated by incumbent Emily Su: negotiate director/VP role under her second term. Run again in 2028-29 when she is definitively gone. MCSS director position as consolation \u2014 maintains insider status.", "status": "planned"},
    {"goal": "Campus Council", "fallback": "Apply for committee appointments through UTMSU. Mekayel can advocate from BOD. Try again next election cycle.", "status": "planned"},
    {"goal": "Pyko ICUBE", "fallback": "Apply to DMZ, CDL, or Creative Destruction Lab instead. Bootstrap through MISTic R&D. Pyko survives without incubator.", "status": "planned"},
    {"goal": "GPA 3.70", "fallback": "If stuck at 3.50, Vector is harder but not impossible. Focus on ML portfolio quality over raw GPA. Consider research assistantship for credibility.", "status": "at-risk"},
    {"goal": "Vector Institute", "fallback": "Apply to Borealis AI, Google Brain Montreal, or MILA internships. Build ML portfolio through UTMIST projects instead.", "status": "planned"},
    {"goal": "UTMIST Position", "fallback": "Contribute to open-source ML projects independently. UTMIST is one path to ML credibility, not the only one.", "status": "planned"},
    {"goal": "Mekayel Alliance", "fallback": "Mekayel lost BOD seat (375 votes, 16th/23). UTMSU VP Internal path is at risk. Fallback: Build direct relationship with IgniteUTM exec, or abandon UTMSU ambition entirely. Mekayel remains valuable as Pyko ambassador only.", "status": "at-risk"},
    {"goal": "Pyko Club", "fallback": "If UTMSU rejects recognition, operate as informal study group. Partner with existing clubs instead of creating a new one.", "status": "planned"},
]

# ════════════════════════════════════════════
# POST-ELECTION ROADMAP (Mar-Aug 2027)
# ════════════════════════════════════════════

POST_ELECTION = [
    {"month": "MAR 2027", "items": [
        {"text": "Transition into MCSS presidency", "key": True},
        {"text": "Meet outgoing exec for knowledge transfer", "key": False},
        {"text": "Set Q1 agenda: DeerHacks 2027 planning", "key": True},
        {"text": "Appoint committee chairs", "key": False},
    ]},
    {"month": "APR 2027", "items": [
        {"text": "First MCSS general meeting as president", "key": True},
        {"text": "Launch Pyko partnership with MCSS events", "key": True},
        {"text": "Begin faculty advisory board outreach", "key": False},
        {"text": "Review MCSS budget and sponsorship pipeline", "key": False},
    ]},
    {"month": "MAY-JUN 2027", "items": [
        {"text": "DeerHacks 2027 execution", "key": True},
        {"text": "Summer programming: career workshops, hackathon series", "key": False},
        {"text": "Vector Institute application prep begins", "key": True},
        {"text": "CSC311 or CSC413 registration", "key": True},
    ]},
    {"month": "JUL-AUG 2027", "items": [
        {"text": "Recruit next MCSS exec generation", "key": False},
        {"text": "Pyko-MCSS joint initiative launch", "key": True},
        {"text": "ML project portfolio building", "key": True},
        {"text": "Network with Vector faculty through UTMIST alumni", "key": False},
    ]},
]

# ════════════════════════════════════════════
# SLATE INTELLIGENCE
# ════════════════════════════════════════════

SLATE_HISTORY = [
    {"year": "2022-23", "slate": "Inspire UTM", "president": "\u2014", "votes": None, "margin": "Sweep", "opposition": "Change UTM"},
    {"year": "2023-24", "slate": "Thrive UTM", "president": "Gulfy Bekbolatova", "votes": 1102, "margin": "+435", "opposition": "It's Time UTM, United UTM"},
    {"year": "2024-25", "slate": "EmpowerUTM", "president": "\u2014", "votes": None, "margin": "Sweep", "opposition": "ForUTM"},
    {"year": "2025-26", "slate": "InnovateUTM", "president": "Andrew Park", "votes": 1683, "margin": "+715", "opposition": "EvolveUTM"},
    {"year": "2026-27", "slate": "IgniteUTM", "president": "Adam El-Falou", "votes": 1501, "margin": "+1111", "opposition": "Independents only"},
]

IGNITEUTM_RESULTS = {
    "executive": [
        {"position": "President", "winner": "Adam El-Falou", "votes": 1501, "runner_up": "Oliver Wang (Ind.)", "runner_up_votes": 390, "pct": 79.4},
        {"position": "VP Internal", "winner": "Freya Gao", "votes": 1505, "runner_up": "Manal Ali (Ind.)", "runner_up_votes": 382, "pct": 79.8},
        {"position": "VP External", "winner": "Rajas Dhamija", "votes": 1520, "runner_up": "George Maafo (Ind.)", "runner_up_votes": 316, "pct": 82.8},
        {"position": "VP Equity", "winner": "Tiffany Da Silva", "votes": 1605, "runner_up": "Against", "runner_up_votes": 90, "pct": 94.7},
        {"position": "VP Univ. Affairs", "winner": "Dana Al-Habash", "votes": 1551, "runner_up": "Mariam Botros (Ind.)", "runner_up_votes": 308, "pct": 83.4},
    ],
    "slate": [
        {"name": "Adam El-Falou", "position": "President", "year": "3rd", "program": "Geospatial Data Sci, CS minor", "prior_role": "BOD Div II (2025-26)", "org_ties": "MSA Advocacy Dir."},
        {"name": "Freya Gao", "position": "VP Internal", "year": "3rd", "program": "Digital Enterprise Mgmt", "prior_role": "BOD Div I, VP Int. Associate", "org_ties": "WeChat Coordinator"},
        {"name": "Rajas Dhamija", "position": "VP External", "year": "3rd", "program": "Commerce & Economics", "prior_role": "VP Ext (InnovateUTM)", "org_ties": "Transit advocacy"},
        {"name": "Tiffany Da Silva", "position": "VP Equity", "year": "3rd", "program": "Digital Enterprise Mgmt", "prior_role": "CSE, IEC, BAEE", "org_ties": "Caribbean Conn., BSA"},
        {"name": "Dana Al-Habash", "position": "VP Univ. Affairs", "year": "4th", "program": "Digital Enterprise Mgmt", "prior_role": "LAUNCH Leader (CSE)", "org_ties": "ICCIT Mentor"},
    ],
    "turnout": 2010, "eligible": 15000, "turnout_pct": 13.4, "avg_margin": 83.8,
}

# ════════════════════════════════════════════
# EXTERNAL NETWORK
# ════════════════════════════════════════════

EXTERNAL_NETWORK = [
    {"name": "Pyko Investors", "role": "Angel investors / seed funders", "domain": "startup", "status": "active", "color": "#a855f7", "action": "Maintain quarterly updates. Leverage for warm intros to other founders."},
    {"name": "ICUBE Mentors", "role": "UTM startup incubator advisors", "domain": "startup", "status": "planned", "color": "#a855f7", "action": "Apply to Venture Forward. Get assigned mentor for Pyko growth strategy."},
    {"name": "Vector Faculty", "role": "ML researchers (target: CSC413 profs)", "domain": "ai_ml", "status": "planned", "color": "#f97316", "action": "Identify 2-3 profs doing ML research. Attend office hours. Ask about summer positions."},
    {"name": "UTMIST Alumni", "role": "Former UTMIST execs now in industry", "domain": "ai_ml", "status": "planned", "color": "#f97316", "action": "Connect via LinkedIn. Ask about Vector application process and ML career paths."},
    {"name": "MCSS Alumni", "role": "Past MCSS presidents/execs", "domain": "mcss", "status": "planned", "color": "#3b82f6", "action": "Find on LinkedIn. Ask about election strategy, common pitfalls, DeerHacks lessons."},
    {"name": "UofT Startup Network", "role": "CDL, DMZ, Rotman founders", "domain": "startup", "status": "planned", "color": "#a855f7", "action": "Attend UofT entrepreneurship events. Build peer network beyond UTM."},
    {"name": "IgniteUTM Executive", "role": "UTMSU 2026-27 exec: El-Falou, Gao, Dhamija, Da Silva, Al-Habash", "domain": "governance", "status": "active", "color": "#10b981", "action": "Swept all 5 exec positions with ~80% margins. They control UTMSU for 2026-27. Must build relationship."},
]

# ════════════════════════════════════════════
# GRAPH NODES (vis.js node definitions)
# ════════════════════════════════════════════

GRAPH_NODES = [
    {"id": "ericsson", "label": "ERICSSON CUI", "group": "center"},
    {"id": "pyko", "label": "PYKO\nDir + Engineer", "group": "pyko"},
    {"id": "mcss", "label": "MCSS\nPresident", "group": "mcss"},
    {"id": "council", "label": "Campus Council\nAcademic Affairs", "group": "council"},
    {"id": "utmist", "label": "UTMIST\nML Developer", "group": "utmist"},
    {"id": "pyko_club", "label": "Pyko Learning\nSociety", "group": "pyko"},
    {"id": "pyko_lab", "label": "PYKO LAB\nParent Entity", "group": "pyko"},
    {"id": "ambassador_program", "label": "Ambassador\nProgram", "group": "pyko"},
    {"id": "mcss_election", "label": "MCSS\nElection", "group": "election"},
    {"id": "mcss_slate", "label": "MCSS\nSlate", "group": "election"},
    {"id": "vp_internal", "label": 'VP Internal\n"The Insider"', "group": "election"},
    {"id": "vp_finance", "label": 'VP Finance\n"Math/Stats Rep"', "group": "election"},
    {"id": "vp_external", "label": 'VP External\n"Tech Credibility"', "group": "election"},
    {"id": "vp_marketing", "label": 'VP Marketing\n"Discord Celebrity"', "group": "election"},
    {"id": "wisc", "label": "WiSC", "group": "partner"},
    {"id": "mathclub", "label": "Math Club", "group": "partner"},
    {"id": "cssc", "label": "CSSC", "group": "partner"},
    {"id": "dsc", "label": "DSC UTM", "group": "partner"},
    {"id": "utmsam", "label": "UTMSAM", "group": "partner"},
    {"id": "mcsdept", "label": "MCS\nDepartment", "group": "inst"},
    {"id": "utmadmin", "label": "UTM\nAdministration", "group": "inst"},
    {"id": "utmsu", "label": "UTMSU", "group": "inst"},
    {"id": "vp_campuslife", "label": "VP Campus\nLife", "group": "inst"},
    {"id": "mekayel", "label": "Mekayel\nOmier", "group": "people"},
    {"id": "ethan", "label": "Ethan Koo", "group": "people"},
    {"id": "raaid", "label": "Raaid\nShabeer", "group": "people"},
    {"id": "saurabh", "label": "Saurabh\nNair", "group": "people"},
    {"id": "henrik", "label": "Henrik\nZimmermann", "group": "people"},
    {"id": "faculty", "label": "Faculty\nAdvisors", "group": "people"},
    {"id": "utmac", "label": "UTMAC\nAthletic Council", "group": "partner"},
    {"id": "icube", "label": "ICUBE\nUTM", "group": "resource"},
    {"id": "mistic", "label": "MISTic\nR&D", "group": "resource"},
    {"id": "deerhacks", "label": "DeerHacks", "group": "resource"},
    {"id": "eigenai", "label": "EigenAI", "group": "resource"},
    {"id": "genai", "label": "GenAI\nGenesis", "group": "resource"},
    {"id": "voting_platform", "label": "SimplyVoting\n(MCSS)", "group": "resource"},
    {"id": "hacklab", "label": "UTM\nHackLab", "group": "resource"},
    {"id": "vector", "label": "Vector\nInstitute", "group": "future"},
    {"id": "courses", "label": "4-YEAR\nROADMAP", "group": "future"},
    {"id": "risks", "label": "RISK\nMATRIX", "group": "election"},
    {"id": "competitors", "label": "THREAT\nASSESSMENT", "group": "election"},
    {"id": "cs_students", "label": "CS\nStudents", "group": "voters"},
    {"id": "math_students", "label": "Math/Stats\nStudents", "group": "voters"},
    {"id": "firstyears", "label": "First-Year\nCohort", "group": "voters"},
    {"id": "discord", "label": "UTM CS\nDiscord", "group": "voters"},
    {"id": "phase1", "label": "Phase 1\nRecon", "group": "timeline"},
    {"id": "phase2", "label": "Phase 2\nInsider", "group": "timeline"},
    {"id": "phase3", "label": "Phase 3\nExpansion", "group": "timeline"},
    {"id": "phase4", "label": "Phase 4-5\nSlate + Win", "group": "timeline"},
    {"id": "keydates", "label": "KEY\nDATES", "group": "timeline"},
    {"id": "vpcl_opportunity", "label": "VP Campus Life\n(Appointed)", "group": "council"},
    {"id": "utmsu_committees", "label": "UTMSU Board\nCommittees", "group": "council"},
    {"id": "workstudy", "label": "Work-Study\n(Opens Mar 30)", "group": "resource"},
    {"id": "campus_affairs", "label": "Campus Affairs\nCommittee", "group": "council"},
    {"id": "orientation", "label": "Orientation\nPathfinder", "group": "voters"},
]

# ════════════════════════════════════════════
# GRAPH EDGES
# ════════════════════════════════════════════

GRAPH_EDGES = [
    # Ericsson direct connections
    {"from": "ericsson", "to": "pyko", "label": "Co-Founder & CTO"},
    {"from": "ericsson", "to": "mcss", "label": "Target: President Feb 2027"},
    {"from": "ericsson", "to": "council", "label": "Ran for CC + AA (results Apr 10)"},
    {"from": "ericsson", "to": "utmist", "label": "Join Discord, apply Sep 2026"},
    {"from": "ericsson", "to": "pyko_club", "label": "President of PLS"},
    {"from": "ericsson", "to": "pyko_lab", "label": "Founding Researcher"},
    {"from": "ericsson", "to": "mekayel", "label": "Political ally + Pyko Ambassador"},
    {"from": "ericsson", "to": "vector", "label": "Summer 2028 target"},
    {"from": "ericsson", "to": "keydates", "label": "Master calendar"},
    {"from": "ericsson", "to": "vpcl_opportunity", "label": "Track VP CL appointment"},
    {"from": "ericsson", "to": "utmsu_committees", "label": "Target Elections committee"},
    {"from": "ericsson", "to": "workstudy", "label": "Apply Mar 30 via CLNx"},
    {"from": "ericsson", "to": "campus_affairs", "label": "Governance entry point"},
    {"from": "ericsson", "to": "orientation", "label": "Voter-facing visibility"},
    {"from": "ericsson", "to": "courses", "label": "CS POSt pathway"},
    {"from": "ericsson", "to": "risks", "label": "6 identified risks"},
    {"from": "ericsson", "to": "competitors", "label": "Emily Su incumbent"},
    {"from": "ericsson", "to": "utmac", "label": "Council member"},
    {"from": "ericsson", "to": "raaid", "label": "Connected via Mekayel"},
    # Pyko ecosystem
    {"from": "pyko", "to": "mcss", "label": "Credibility + user acquisition"},
    {"from": "pyko", "to": "icube", "label": "Free workspace, no equity"},
    {"from": "pyko", "to": "mistic", "label": "Free AI incubator"},
    {"from": "pyko", "to": "ambassador_program", "label": "Campus ops division"},
    {"from": "pyko_lab", "to": "pyko", "label": "Parent — golden share"},
    {"from": "pyko_lab", "to": "pyko_club", "label": "Researchers speak at PLS"},
    # MCSS web
    {"from": "mcss", "to": "council", "label": "Dual representation"},
    {"from": "mcss", "to": "utmist", "label": "DeerHacks x EigenAI cross-promo"},
    {"from": "mcss", "to": "wisc", "label": "Partner, co-host events"},
    {"from": "mcss", "to": "mathclub", "label": "Recruit Math slate members"},
    {"from": "mcss", "to": "cssc", "label": "Coordinate, don't duplicate"},
    {"from": "mcss", "to": "dsc", "label": "Joint workshops"},
    {"from": "mcss", "to": "utmsam", "label": "LeetQuest = engaged voters"},
    {"from": "mcss", "to": "mcsdept", "label": "Faculty advisor relationship"},
    {"from": "mcss", "to": "utmsu", "label": "ASAC oversight + funding"},
    {"from": "mcss", "to": "deerhacks", "label": "President oversees DeerHacks"},
    {"from": "mcss", "to": "mcss_election", "label": "Election determines leadership"},
    # Council web
    {"from": "council", "to": "pyko", "label": "63-member networking goldmine"},
    {"from": "council", "to": "mcsdept", "label": "Dual-channel faculty access"},
    {"from": "council", "to": "utmadmin", "label": "Direct line to VP Principal"},
    # UTMIST web
    {"from": "utmist", "to": "pyko", "label": "70+ ML devs hiring pipeline"},
    {"from": "pyko", "to": "utmist", "label": "Pyko ML features as portfolio"},
    {"from": "utmist", "to": "eigenai", "label": "Flagship AI conference"},
    {"from": "utmist", "to": "genai", "label": "700+ participant hackathon"},
    {"from": "utmist", "to": "vector", "label": "Feeder pipeline to Vector"},
    {"from": "mistic", "to": "utmist", "label": "Run by UTMIST"},
    # Election mechanics
    {"from": "mcss_election", "to": "mcss_slate", "label": "Slate runs together"},
    {"from": "mcss_election", "to": "voting_platform", "label": "SimplyVoting (confirmed)"},
    {"from": "mcss_election", "to": "utmsu", "label": "ASAC overwatch"},
    {"from": "mcss_slate", "to": "vp_internal", "label": "The Insider archetype"},
    {"from": "mcss_slate", "to": "vp_finance", "label": "Math/Stats Rep"},
    {"from": "mcss_slate", "to": "vp_external", "label": "Technical Credibility"},
    {"from": "mcss_slate", "to": "vp_marketing", "label": "Discord Celebrity"},
    {"from": "wisc", "to": "vp_internal", "label": "#1 recruitment source"},
    {"from": "vp_external", "to": "deerhacks", "label": "Source for candidates"},
    {"from": "competitors", "to": "mcss_election", "label": "Incumbent threat"},
    {"from": "competitors", "to": "mcss_slate", "label": "Cannot recruit Emily"},
    {"from": "risks", "to": "mcss_election", "label": "Risks #1, #3, #5"},
    {"from": "risks", "to": "council", "label": "Risk #4: lose seats"},
    # People
    {"from": "ethan", "to": "pyko", "label": "Co-founder & lead engineer"},
    {"from": "ethan", "to": "mcss_election", "label": "Builds campaign website"},
    {"from": "mekayel", "to": "ambassador_program", "label": "Lead ambassador"},
    {"from": "mekayel", "to": "pyko", "label": "Campus Ambassador"},
    {"from": "mekayel", "to": "pyko_club", "label": "BOD knowledge for recognition"},
    {"from": "mekayel", "to": "council", "label": "GC election alliance"},
    {"from": "mekayel", "to": "mcss", "label": "Voter + campaign advocate"},
    {"from": "mekayel", "to": "vp_campuslife", "label": "Narrow window for appointment"},
    {"from": "mekayel", "to": "utmsu", "label": "Outgoing Div I director"},
    {"from": "mekayel", "to": "utmsu_committees", "label": "Bridge via Maryam Zeeshan"},
    {"from": "mekayel", "to": "utmac", "label": "Athletic network"},
    {"from": "raaid", "to": "utmac", "label": "Core UTMAC member"},
    {"from": "raaid", "to": "mekayel", "label": "Fellow ally"},
    {"from": "saurabh", "to": "mcss", "label": "Outgoing president 2025-26"},
    {"from": "saurabh", "to": "mcss_election", "label": "His team ran 2026-27 election"},
    {"from": "henrik", "to": "mcss", "label": "Former president, slate model"},
    {"from": "henrik", "to": "saurabh", "label": "Saurabh was on Henrik's slate"},
    {"from": "faculty", "to": "mcss", "label": "Zhang, Holden, Aslemand advise"},
    {"from": "faculty", "to": "council", "label": "Faculty sit on AA committee"},
    {"from": "faculty", "to": "mcsdept", "label": "Bridge between dept and MCSS"},
    # Voter blocs
    {"from": "cs_students", "to": "mcss", "label": "Largest voter bloc"},
    {"from": "cs_students", "to": "discord", "label": "Primary online community"},
    {"from": "math_students", "to": "mcss", "label": "Underserved voter bloc"},
    {"from": "math_students", "to": "vp_finance", "label": "Unlocked by Math/Stats Rep"},
    {"from": "firstyears", "to": "mcss", "label": "Natural network"},
    {"from": "firstyears", "to": "mcss_slate", "label": "Primary recruitment pool"},
    {"from": "discord", "to": "mcss", "label": "2,800+ members, 30-50 votes"},
    {"from": "discord", "to": "voting_platform", "label": "Post link = 56+ votes"},
    {"from": "discord", "to": "vp_marketing", "label": "Must be active here"},
    {"from": "orientation", "to": "firstyears", "label": "Direct voter contact"},
    # Phases
    {"from": "phase1", "to": "phase2", "label": "Recon feeds insider"},
    {"from": "phase2", "to": "phase3", "label": "Insider enables expansion"},
    {"from": "phase3", "to": "phase4", "label": "Expansion enables winning"},
    {"from": "phase1", "to": "mcss", "label": "Email mcss@utmsu.ca"},
    {"from": "phase1", "to": "utmist", "label": "Join UTMIST Discord"},
    {"from": "phase1", "to": "mistic", "label": "Submit Pyko to MISTic"},
    {"from": "phase1", "to": "icube", "label": "Email ICUBE"},
    {"from": "phase1", "to": "council", "label": "Apr 10 results"},
    # Institutional
    {"from": "vp_campuslife", "to": "utmsu", "label": "Appointed by BOD"},
    {"from": "vp_campuslife", "to": "mcss", "label": "Liaises with societies"},
    {"from": "pyko_club", "to": "utmsu", "label": "Club recognition + funding"},
    {"from": "pyko_club", "to": "vp_campuslife", "label": "Reviews club application"},
    {"from": "pyko_club", "to": "mcss", "label": "Club Connection Fund joint events"},
    {"from": "pyko_club", "to": "wisc", "label": "Joint events via CCF"},
    {"from": "pyko_club", "to": "deerhacks", "label": "Co-host study workshops"},
    {"from": "ambassador_program", "to": "cssc", "label": "Sponsorship target"},
    {"from": "ambassador_program", "to": "mcss", "label": "Sponsorship target"},
    # Resources & future
    {"from": "vector", "to": "utmist", "label": "UTMIST sponsors overlap"},
    {"from": "vector", "to": "pyko", "label": "Applied ML portfolio"},
    {"from": "deerhacks", "to": "dsc", "label": "DSC members participate"},
    {"from": "hacklab", "to": "mcss_election", "label": "Flyering location"},
    {"from": "courses", "to": "vector", "label": "CSC311 + CSC413 gateway"},
    {"from": "courses", "to": "faculty", "label": "Course \u2192 advisor pipeline"},
    {"from": "keydates", "to": "mcss_election", "label": "End of Feb 2027"},
    {"from": "keydates", "to": "pyko_club", "label": "SOP May 1 - Jul 31"},
    {"from": "keydates", "to": "council", "label": "Apr 10 results"},
    {"from": "workstudy", "to": "mcsdept", "label": "Faculty relationship building"},
    {"from": "campus_affairs", "to": "council", "label": "12 shared seats"},
    {"from": "vpcl_opportunity", "to": "utmsu", "label": "Appointed by BOD"},
]

# ════════════════════════════════════════════
# EDGE WEIGHTS (relationship metadata)
# ════════════════════════════════════════════

EDGE_WEIGHTS: dict[str, dict] = {
    "ericsson->pyko": {"strength": 5, "trust": 5, "leverage": "mutual", "trajectory": "stable", "note": "Co-founder. Highest-trust relationship."},
    "ericsson->mcss": {"strength": 2, "trust": 2, "leverage": "ericsson_needs", "trajectory": "improving", "note": "Target org. No relationship yet."},
    "ericsson->council": {"strength": 2, "trust": 3, "leverage": "mutual", "trajectory": "pending", "note": "Ran but results pending."},
    "ericsson->utmist": {"strength": 1, "trust": 1, "leverage": "ericsson_needs", "trajectory": "not_started", "note": "No contact yet."},
    "ericsson->mekayel": {"strength": 2, "trust": 3, "leverage": "mutual", "trajectory": "declining", "note": "Lost Div II re-election. Presidential ambition weakened."},
    "ericsson->vector": {"strength": 1, "trust": 1, "leverage": "ericsson_needs", "trajectory": "not_started", "note": "Long-term aspiration."},
    "pyko->mcss": {"strength": 3, "trust": 2, "leverage": "pyko_gives", "trajectory": "planned", "note": "Credibility + distribution exchange."},
    "mcss->council": {"strength": 3, "trust": 3, "leverage": "mutual", "trajectory": "planned", "note": "Dual representation advantage."},
    "utmist->pyko": {"strength": 3, "trust": 2, "leverage": "mutual", "trajectory": "planned", "note": "ML talent pipeline exchange."},
    "ericsson->pyko_club": {"strength": 3, "trust": 4, "leverage": "ericsson_controls", "trajectory": "improving", "note": "Ericsson controls this entity."},
    "ericsson->pyko_lab": {"strength": 2, "trust": 3, "leverage": "advisory", "trajectory": "improving", "note": "Non-executive role."},
}

# ════════════════════════════════════════════
# GROUP LABELS & COLORS
# ════════════════════════════════════════════

GROUP_LABELS = {
    "center": "Ericsson Cui", "pyko": "Pyko (Startup)", "mcss": "MCSS (Society)",
    "council": "Governance", "utmist": "UTMIST (AI/ML)", "election": "Election Mechanics",
    "partner": "Partner Orgs", "inst": "Institutional", "resource": "Resources",
    "people": "People", "voters": "Voter Blocs", "timeline": "Timeline Phases", "future": "Future Goals",
}

GROUP_COLORS = {
    "center": "#a882ff", "pyko": "#a882ff", "mcss": "#7c9aff", "council": "#6bc9a0",
    "utmist": "#e0a060", "election": "#e06080", "partner": "#8a9bb0", "inst": "#a0aec0",
    "resource": "#6dd8e8", "people": "#c89df0", "voters": "#f0889a", "timeline": "#7ce8e8", "future": "#e8d06c",
}

# ════════════════════════════════════════════
# CAMPUS MAP LOCATIONS
# ════════════════════════════════════════════

LOCATIONS = {
    "utmsu_office": {"name": "UTMSU Office", "building": "Student Centre", "lat": 43.548823, "lng": -79.664029, "entities": ["utmsu", "mekayel"], "type": "governance", "description": "Student union HQ \u2014 governance/election operations"},
    "mcs_dept": {"name": "MCS Department", "building": "Deerfield Hall", "lat": 43.550433, "lng": -79.666281, "entities": ["mcss", "courses"], "type": "academic", "description": "CS department \u2014 MCSS home base, academic hub"},
    "innovation_complex": {"name": "Innovation Complex", "building": "ICUBE / IC", "lat": 43.548595, "lng": -79.662936, "entities": ["pyko", "icube"], "type": "startup", "description": "Startup incubator \u2014 Pyko operations"},
    "davis_building": {"name": "Davis Building", "building": "Wm. G. Davis Building", "lat": 43.548513, "lng": -79.661521, "entities": ["council"], "type": "governance", "description": "Campus governance, academic affairs, lecture halls"},
    "hazel_mccallion": {"name": "Library", "building": "Hazel McCallion Academic Learning Centre", "lat": 43.550880, "lng": -79.662851, "entities": ["courses", "firstyears"], "type": "academic", "description": "Main campus library \u2014 study hub, group work, poster boards"},
    "instructional_centre": {"name": "Instructional Centre", "building": "IB Building", "lat": 43.551489, "lng": -79.663941, "entities": ["courses", "firstyears"], "type": "academic", "description": "Large lecture halls \u2014 first-year courses, high foot traffic"},
    "maanjiwe_nendamowinan": {"name": "MN Building", "building": "Maanjiwe nendamowinan", "lat": 43.551047, "lng": -79.665837, "entities": ["mcsdept", "faculty"], "type": "academic", "description": "CS/Math faculty offices, tutorial rooms, department admin"},
    "rawc": {"name": "RAWC", "building": "Recreation, Athletics & Wellness Centre", "lat": 43.547974, "lng": -79.660978, "entities": ["utmac", "raaid"], "type": "social", "description": "Athletics centre \u2014 UTMAC home base, intramural sports"},
    "kaneff_centre": {"name": "Kaneff Centre", "building": "Kaneff Centre", "lat": 43.548317, "lng": -79.663128, "entities": ["council"], "type": "governance", "description": "Adjacent to IC \u2014 academic admin, meeting rooms"},
    "cct_building": {"name": "CCT Building", "building": "Communication, Culture & Technology", "lat": 43.549715, "lng": -79.663029, "entities": ["courses"], "type": "academic", "description": "Tutorial rooms, digital media labs, some CS tutorials"},
    "deerhacks_venue": {"name": "DeerHacks Venue", "building": "Student Centre", "lat": 43.548900, "lng": -79.664100, "entities": ["deerhacks", "mcss"], "type": "event", "description": "DeerHacks hackathon \u2014 160+ participants, 36 hours"},
    "mcss_hub": {"name": "MCSS Hub", "building": "Deerfield Hall \u2014 HackLab 2014", "lat": 43.550500, "lng": -79.666100, "entities": ["mcss", "cs_students"], "type": "social", "description": "MCSS meeting space, HackLab co-working, campaign flyering"},
    "council_chamber": {"name": "Council Chamber", "building": "Wm. G. Davis Building", "lat": 43.548550, "lng": -79.661600, "entities": ["council", "utmadmin"], "type": "governance", "description": "Campus Council meetings \u2014 28 members, 5 times/year"},
}

PEOPLE_LOCATIONS = {
    "mekayel": {"entity_id": "mekayel", "name": "Mekayel Omier", "initials": "MO", "lat": 43.548823, "lng": -79.664029, "role": "Former UTMSU Div I Director | Pyko Ambassador"},
    "saurabh": {"entity_id": "saurabh", "name": "Saurabh Nair", "initials": "SN", "lat": 43.550550, "lng": -79.666400, "role": "MCSS President (2025-26, outgoing)"},
    "emily_su": {"entity_id": "competitors", "name": "Emily Su", "initials": "ES", "lat": 43.550350, "lng": -79.666050, "role": "MCSS President (2026-27) | Incumbent Threat"},
    "raaid": {"entity_id": "raaid", "name": "Raaid Shabeer", "initials": "RS", "lat": 43.549050, "lng": -79.664150, "role": "UTMAC | CS/Math/Stats"},
    "ethan": {"entity_id": "ethan", "name": "Ethan Koo", "initials": "EK", "lat": 43.546763, "lng": -79.664781, "role": "Pyko CEO"},
    "lisa_zhang": {"entity_id": "faculty", "name": "Lisa Zhang", "initials": "LZ", "lat": 43.551150, "lng": -79.665950, "role": "CS Faculty | MCSS Advisor"},
    "tyler_holden": {"entity_id": "faculty", "name": "Tyler Holden", "initials": "TH", "lat": 43.550433, "lng": -79.666281, "role": "Math Faculty | MCSS Advisor"},
}

VOTER_HEATMAP_POINTS = [
    {"lat": 43.550433, "lng": -79.666281, "weight": 80, "bloc": "cs_students"},
    {"lat": 43.550500, "lng": -79.666100, "weight": 60, "bloc": "cs_students"},
    {"lat": 43.551047, "lng": -79.665837, "weight": 40, "bloc": "cs_students"},
    {"lat": 43.548823, "lng": -79.664029, "weight": 50, "bloc": "firstyears"},
    {"lat": 43.551489, "lng": -79.663941, "weight": 70, "bloc": "firstyears"},
    {"lat": 43.550880, "lng": -79.662851, "weight": 45, "bloc": "firstyears"},
    {"lat": 43.548513, "lng": -79.661521, "weight": 50, "bloc": "math_students"},
    {"lat": 43.551047, "lng": -79.665837, "weight": 35, "bloc": "math_students"},
    {"lat": 43.550433, "lng": -79.666281, "weight": 15, "bloc": "discord"},
    {"lat": 43.548823, "lng": -79.664029, "weight": 15, "bloc": "discord"},
    {"lat": 43.551489, "lng": -79.663941, "weight": 15, "bloc": "discord"},
    {"lat": 43.548513, "lng": -79.661521, "weight": 15, "bloc": "discord"},
    {"lat": 43.550880, "lng": -79.662851, "weight": 15, "bloc": "discord"},
    {"lat": 43.547974, "lng": -79.660978, "weight": 10, "bloc": "discord"},
    {"lat": 43.549715, "lng": -79.663029, "weight": 10, "bloc": "discord"},
    {"lat": 43.548317, "lng": -79.663128, "weight": 10, "bloc": "discord"},
]

PHASE_LOCATION_RELEVANCE = {
    "recon": {
        "utmsu_office": "Monitor UTMSU election results",
        "mcs_dept": "Email mcss@utmsu.ca for constitution",
        "innovation_complex": "Submit Pyko to MISTic R&D, email ICUBE",
        "davis_building": "Apr 10 governance results",
        "council_chamber": "Campus Council + AA election results",
    },
    "insider": {
        "mcs_dept": "Apply for MCSS director/associate role",
        "mcss_hub": "Begin attending MCSS meetings",
        "innovation_complex": "ICUBE Venture Forward enrollment",
        "utmsu_office": "Society training, Pyko SOP application",
        "maanjiwe_nendamowinan": "Faculty relationship building begins",
    },
    "expansion": {
        "mcs_dept": "Visible at every MCSS event",
        "mcss_hub": "Scout slate candidates from 2nd-year cohort",
        "deerhacks_venue": "Source for VP External candidates",
        "instructional_centre": "First-year recruitment \u2014 high traffic",
        "hazel_mccallion": "Coffee chats with potential slate members",
        "rawc": "UTMAC involvement, athletic voter base",
    },
    "slate": {
        "mcs_dept": "Lock slate, campaign headquarters",
        "mcss_hub": "Campaign flyering at HackLab",
        "deerhacks_venue": "DeerHacks 2027 oversight as credibility",
        "utmsu_office": "CRO coordination, election compliance",
        "instructional_centre": "Campaign outreach \u2014 lecture hall exits",
        "hazel_mccallion": "Poster distribution, study break campaigning",
        "council_chamber": "Leverage governance credibility",
    },
}

# ════════════════════════════════════════════
# LOCATION TYPE COLORS
# ════════════════════════════════════════════

LOCATION_TYPE_COLORS = {
    "governance": "#238551",
    "academic": "#00D4FF",
    "startup": "#a855f7",
    "event": "#f97316",
    "social": "#f0889a",
}
