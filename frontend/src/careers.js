// GENERATED from TestMind's assets/careers-data.js and assets/recommend.js.
// Do not edit by hand -- regenerate with scratchpad/gen_careers.js.
//
// 96 careers, 55 majors and 16 families, each carrying a RIASEC profile,
// a work-values profile and the school subjects it leans on. No salaries and no
// demand ratings: there is no Uzbek labour-market data behind them, so claiming
// any would be invention.
//
// The scorer below is TestMind's, copied rather than reimplemented so the two
// products can never rank the same student differently. Its comments explain
// every weight; read them before changing a number.

export const CAREER_FAMILIES = {
 "agriculture": {
  "riasec": {
   "C": 0.2,
   "I": 0.3,
   "R": 0.5
  },
  "subjects": {
   "biology": 0.5,
   "chemistry": 0.3,
   "geography": 0.2
  },
  "values": {
   "balance": 0.2,
   "independence": 0.25,
   "meaning": 0.3,
   "stability": 0.25
  }
 },
 "architecture": {
  "riasec": {
   "A": 0.5,
   "I": 0.2,
   "R": 0.3
  },
  "subjects": {
   "art": 0.4,
   "math": 0.3,
   "physics": 0.3
  },
  "values": {
   "creativity": 0.45,
   "income": 0.15,
   "independence": 0.25,
   "meaning": 0.15
  }
 },
 "arts": {
  "riasec": {
   "A": 0.8,
   "E": 0.1,
   "S": 0.1
  },
  "subjects": {
   "art": 0.7,
   "literature": 0.3
  },
  "values": {
   "creativity": 0.5,
   "independence": 0.3,
   "meaning": 0.2
  }
 },
 "business": {
  "riasec": {
   "C": 0.2,
   "E": 0.6,
   "S": 0.2
  },
  "subjects": {
   "economics": 0.4,
   "english": 0.3,
   "math": 0.3
  },
  "values": {
   "creativity": 0.15,
   "income": 0.3,
   "independence": 0.25,
   "leadership": 0.3
  }
 },
 "cs": {
  "riasec": {
   "C": 0.2,
   "I": 0.5,
   "R": 0.3
  },
  "subjects": {
   "cs": 0.4,
   "math": 0.4,
   "physics": 0.2
  },
  "values": {
   "creativity": 0.2,
   "income": 0.2,
   "independence": 0.25,
   "learning": 0.35
  }
 },
 "education": {
  "riasec": {
   "A": 0.2,
   "C": 0.1,
   "S": 0.7
  },
  "subjects": {
   "english": 0.3,
   "history": 0.3,
   "literature": 0.4
  },
  "values": {
   "balance": 0.2,
   "helping": 0.35,
   "meaning": 0.3,
   "stability": 0.15
  }
 },
 "engineering": {
  "riasec": {
   "C": 0.1,
   "I": 0.4,
   "R": 0.5
  },
  "subjects": {
   "cs": 0.2,
   "math": 0.4,
   "physics": 0.4
  },
  "values": {
   "income": 0.25,
   "learning": 0.3,
   "stability": 0.25,
   "teamwork": 0.2
  }
 },
 "finance": {
  "riasec": {
   "C": 0.5,
   "E": 0.2,
   "I": 0.3
  },
  "subjects": {
   "cs": 0.1,
   "economics": 0.4,
   "math": 0.5
  },
  "values": {
   "income": 0.4,
   "learning": 0.25,
   "stability": 0.35
  }
 },
 "hospitality": {
  "riasec": {
   "C": 0.2,
   "E": 0.4,
   "S": 0.4
  },
  "subjects": {
   "economics": 0.2,
   "english": 0.5,
   "geography": 0.3
  },
  "values": {
   "creativity": 0.2,
   "helping": 0.25,
   "income": 0.2,
   "teamwork": 0.35
  }
 },
 "law": {
  "riasec": {
   "C": 0.3,
   "E": 0.4,
   "S": 0.3
  },
  "subjects": {
   "economics": 0.3,
   "history": 0.4,
   "literature": 0.3
  },
  "values": {
   "income": 0.25,
   "leadership": 0.25,
   "meaning": 0.25,
   "stability": 0.25
  }
 },
 "logistics": {
  "riasec": {
   "C": 0.4,
   "E": 0.2,
   "R": 0.4
  },
  "subjects": {
   "geography": 0.3,
   "math": 0.4,
   "physics": 0.3
  },
  "values": {
   "balance": 0.2,
   "income": 0.25,
   "stability": 0.35,
   "teamwork": 0.2
  }
 },
 "media": {
  "riasec": {
   "A": 0.5,
   "E": 0.3,
   "S": 0.2
  },
  "subjects": {
   "art": 0.2,
   "english": 0.3,
   "literature": 0.5
  },
  "values": {
   "creativity": 0.4,
   "independence": 0.25,
   "meaning": 0.2,
   "teamwork": 0.15
  }
 },
 "medicine": {
  "riasec": {
   "I": 0.4,
   "R": 0.2,
   "S": 0.4
  },
  "subjects": {
   "biology": 0.5,
   "chemistry": 0.4,
   "physics": 0.1
  },
  "values": {
   "helping": 0.4,
   "learning": 0.2,
   "meaning": 0.25,
   "stability": 0.15
  }
 },
 "psychology": {
  "riasec": {
   "A": 0.1,
   "I": 0.3,
   "S": 0.6
  },
  "subjects": {
   "biology": 0.4,
   "history": 0.3,
   "literature": 0.3
  },
  "values": {
   "helping": 0.45,
   "learning": 0.25,
   "meaning": 0.3
  }
 },
 "science": {
  "riasec": {
   "A": 0.1,
   "I": 0.7,
   "R": 0.2
  },
  "subjects": {
   "biology": 0.2,
   "chemistry": 0.3,
   "math": 0.2,
   "physics": 0.3
  },
  "values": {
   "independence": 0.3,
   "learning": 0.45,
   "meaning": 0.25
  }
 },
 "sport": {
  "riasec": {
   "E": 0.3,
   "R": 0.4,
   "S": 0.3
  },
  "subjects": {
   "biology": 0.6,
   "english": 0.2,
   "geography": 0.2
  },
  "values": {
   "balance": 0.25,
   "helping": 0.25,
   "meaning": 0.2,
   "teamwork": 0.3
  }
 }
}

export const CAREER_ENTRIES = {
 "accountant": {
  "education": "either",
  "family": "finance",
  "riasec": {
   "C": 0.7,
   "E": 0.1,
   "I": 0.2
  },
  "subjects": {
   "cs": 0.1,
   "economics": 0.4,
   "math": 0.5
  },
  "values": {
   "balance": 0.2,
   "income": 0.25,
   "stability": 0.4,
   "teamwork": 0.15
  }
 },
 "actor": {
  "education": "either",
  "family": "arts",
  "riasec": {
   "A": 0.7,
   "E": 0.2,
   "S": 0.1
  },
  "subjects": {
   "art": 0.5,
   "literature": 0.5
  },
  "values": {
   "creativity": 0.5,
   "independence": 0.2,
   "meaning": 0.15,
   "teamwork": 0.15
  }
 },
 "agronomist": {
  "education": "either",
  "family": "agriculture",
  "riasec": {
   "C": 0.15,
   "I": 0.35,
   "R": 0.5
  },
  "subjects": {
   "biology": 0.5,
   "chemistry": 0.3,
   "geography": 0.2
  },
  "values": {
   "balance": 0.2,
   "independence": 0.25,
   "meaning": 0.3,
   "stability": 0.25
  }
 },
 "ai_engineer": {
  "education": "higher",
  "family": "cs",
  "riasec": {
   "C": 0.1,
   "I": 0.7,
   "R": 0.2
  },
  "subjects": {
   "cs": 0.4,
   "math": 0.5,
   "physics": 0.1
  },
  "values": {
   "creativity": 0.1,
   "income": 0.2,
   "independence": 0.25,
   "learning": 0.45
  }
 },
 "animator": {
  "education": "either",
  "family": "arts",
  "riasec": {
   "A": 0.7,
   "I": 0.2,
   "R": 0.1
  },
  "subjects": {
   "art": 0.6,
   "cs": 0.3,
   "literature": 0.1
  },
  "values": {
   "creativity": 0.5,
   "income": 0.1,
   "independence": 0.2,
   "learning": 0.2
  }
 },
 "architect": {
  "education": "higher",
  "family": "architecture",
  "riasec": {
   "A": 0.5,
   "I": 0.2,
   "R": 0.3
  },
  "subjects": {
   "art": 0.4,
   "math": 0.3,
   "physics": 0.3
  },
  "values": {
   "creativity": 0.45,
   "income": 0.15,
   "independence": 0.25,
   "meaning": 0.15
  }
 },
 "artist": {
  "education": "either",
  "family": "arts",
  "riasec": {
   "A": 0.85,
   "E": 0.05,
   "I": 0.1
  },
  "subjects": {
   "art": 0.8,
   "literature": 0.2
  },
  "values": {
   "creativity": 0.55,
   "independence": 0.3,
   "meaning": 0.15
  }
 },
 "athlete": {
  "education": "either",
  "family": "sport",
  "riasec": {
   "E": 0.25,
   "R": 0.55,
   "S": 0.2
  },
  "subjects": {
   "biology": 0.7,
   "english": 0.15,
   "geography": 0.15
  },
  "values": {
   "income": 0.25,
   "independence": 0.3,
   "meaning": 0.25,
   "teamwork": 0.2
  }
 },
 "auditor": {
  "education": "higher",
  "family": "finance",
  "riasec": {
   "C": 0.6,
   "E": 0.1,
   "I": 0.3
  },
  "subjects": {
   "cs": 0.1,
   "economics": 0.4,
   "math": 0.5
  },
  "values": {
   "income": 0.25,
   "independence": 0.2,
   "meaning": 0.2,
   "stability": 0.35
  }
 },
 "banker": {
  "education": "either",
  "family": "finance",
  "riasec": {
   "C": 0.4,
   "E": 0.4,
   "S": 0.2
  },
  "subjects": {
   "cs": 0.1,
   "economics": 0.4,
   "math": 0.5
  },
  "values": {
   "income": 0.35,
   "leadership": 0.15,
   "stability": 0.3,
   "teamwork": 0.2
  }
 },
 "biologist": {
  "education": "higher",
  "family": "science",
  "riasec": {
   "I": 0.7,
   "R": 0.2,
   "S": 0.1
  },
  "subjects": {
   "biology": 0.6,
   "chemistry": 0.3,
   "math": 0.1
  },
  "values": {
   "independence": 0.3,
   "learning": 0.4,
   "meaning": 0.3
  }
 },
 "business_analyst": {
  "education": "higher",
  "family": "business",
  "riasec": {
   "C": 0.4,
   "E": 0.2,
   "I": 0.4
  },
  "subjects": {
   "cs": 0.2,
   "economics": 0.4,
   "math": 0.4
  },
  "values": {
   "income": 0.25,
   "learning": 0.3,
   "stability": 0.3,
   "teamwork": 0.15
  }
 },
 "chef": {
  "education": "college",
  "family": "hospitality",
  "riasec": {
   "A": 0.4,
   "E": 0.2,
   "R": 0.4
  },
  "subjects": {
   "biology": 0.3,
   "chemistry": 0.4,
   "economics": 0.3
  },
  "values": {
   "creativity": 0.4,
   "income": 0.2,
   "independence": 0.15,
   "teamwork": 0.25
  }
 },
 "chemist": {
  "education": "higher",
  "family": "science",
  "riasec": {
   "C": 0.1,
   "I": 0.7,
   "R": 0.2
  },
  "subjects": {
   "chemistry": 0.6,
   "math": 0.2,
   "physics": 0.2
  },
  "values": {
   "income": 0.1,
   "independence": 0.3,
   "learning": 0.4,
   "meaning": 0.2
  }
 },
 "civil_engineer": {
  "education": "higher",
  "family": "engineering",
  "riasec": {
   "C": 0.3,
   "I": 0.2,
   "R": 0.5
  },
  "subjects": {
   "cs": 0.2,
   "math": 0.4,
   "physics": 0.4
  },
  "values": {
   "income": 0.25,
   "meaning": 0.2,
   "stability": 0.3,
   "teamwork": 0.25
  }
 },
 "coach": {
  "education": "either",
  "family": "sport",
  "riasec": {
   "E": 0.25,
   "R": 0.35,
   "S": 0.4
  },
  "subjects": {
   "biology": 0.6,
   "english": 0.3,
   "geography": 0.1
  },
  "values": {
   "balance": 0.2,
   "helping": 0.3,
   "meaning": 0.2,
   "teamwork": 0.3
  }
 },
 "construction_manager": {
  "education": "higher",
  "family": "logistics",
  "riasec": {
   "C": 0.3,
   "E": 0.35,
   "R": 0.35
  },
  "subjects": {
   "geography": 0.2,
   "math": 0.4,
   "physics": 0.4
  },
  "values": {
   "income": 0.3,
   "leadership": 0.3,
   "stability": 0.2,
   "teamwork": 0.2
  }
 },
 "copywriter": {
  "education": "either",
  "family": "media",
  "riasec": {
   "A": 0.6,
   "E": 0.25,
   "I": 0.15
  },
  "subjects": {
   "art": 0.1,
   "english": 0.3,
   "literature": 0.6
  },
  "values": {
   "balance": 0.1,
   "creativity": 0.45,
   "income": 0.15,
   "independence": 0.3
  }
 },
 "cybersecurity": {
  "education": "either",
  "family": "cs",
  "riasec": {
   "C": 0.4,
   "I": 0.5,
   "R": 0.1
  },
  "subjects": {
   "cs": 0.4,
   "math": 0.4,
   "physics": 0.2
  },
  "values": {
   "income": 0.25,
   "learning": 0.3,
   "meaning": 0.15,
   "stability": 0.3
  }
 },
 "data_scientist": {
  "education": "higher",
  "family": "cs",
  "riasec": {
   "A": 0.1,
   "C": 0.3,
   "I": 0.6
  },
  "subjects": {
   "cs": 0.3,
   "economics": 0.2,
   "math": 0.5
  },
  "values": {
   "income": 0.25,
   "independence": 0.3,
   "learning": 0.45
  }
 },
 "dentist": {
  "education": "higher",
  "family": "medicine",
  "riasec": {
   "I": 0.25,
   "R": 0.4,
   "S": 0.35
  },
  "subjects": {
   "biology": 0.5,
   "chemistry": 0.4,
   "physics": 0.1
  },
  "values": {
   "helping": 0.3,
   "income": 0.3,
   "independence": 0.2,
   "stability": 0.2
  }
 },
 "diplomat": {
  "education": "higher",
  "family": "law",
  "riasec": {
   "E": 0.4,
   "I": 0.25,
   "S": 0.35
  },
  "subjects": {
   "english": 0.4,
   "history": 0.35,
   "literature": 0.25
  },
  "values": {
   "income": 0.2,
   "leadership": 0.25,
   "learning": 0.25,
   "meaning": 0.3
  }
 },
 "doctor": {
  "education": "higher",
  "family": "medicine",
  "riasec": {
   "I": 0.4,
   "R": 0.2,
   "S": 0.4
  },
  "subjects": {
   "biology": 0.5,
   "chemistry": 0.4,
   "physics": 0.1
  },
  "values": {
   "helping": 0.4,
   "learning": 0.2,
   "meaning": 0.25,
   "stability": 0.15
  }
 },
 "ecologist": {
  "education": "higher",
  "family": "agriculture",
  "riasec": {
   "I": 0.45,
   "R": 0.3,
   "S": 0.25
  },
  "subjects": {
   "biology": 0.5,
   "chemistry": 0.2,
   "geography": 0.3
  },
  "values": {
   "balance": 0.1,
   "independence": 0.25,
   "learning": 0.2,
   "meaning": 0.45
  }
 },
 "editor": {
  "education": "higher",
  "family": "media",
  "riasec": {
   "A": 0.45,
   "C": 0.35,
   "S": 0.2
  },
  "subjects": {
   "english": 0.3,
   "history": 0.1,
   "literature": 0.6
  },
  "values": {
   "creativity": 0.35,
   "independence": 0.25,
   "meaning": 0.2,
   "stability": 0.2
  }
 },
 "electrical_engineer": {
  "education": "higher",
  "family": "engineering",
  "riasec": {
   "C": 0.1,
   "I": 0.5,
   "R": 0.4
  },
  "subjects": {
   "cs": 0.2,
   "math": 0.4,
   "physics": 0.4
  },
  "values": {
   "income": 0.25,
   "learning": 0.35,
   "stability": 0.25,
   "teamwork": 0.15
  }
 },
 "electrician": {
  "education": "college",
  "family": "logistics",
  "riasec": {
   "C": 0.2,
   "E": 0.1,
   "R": 0.7
  },
  "subjects": {
   "geography": 0.1,
   "math": 0.4,
   "physics": 0.5
  },
  "values": {
   "balance": 0.15,
   "income": 0.3,
   "independence": 0.25,
   "stability": 0.3
  }
 },
 "entrepreneur": {
  "education": "either",
  "family": "business",
  "riasec": {
   "A": 0.1,
   "C": 0.2,
   "E": 0.7
  },
  "subjects": {
   "economics": 0.4,
   "english": 0.3,
   "math": 0.3
  },
  "values": {
   "income": 0.3,
   "independence": 0.35,
   "leadership": 0.25,
   "stability": 0.1
  }
 },
 "environmental_scientist": {
  "education": "higher",
  "family": "science",
  "riasec": {
   "I": 0.5,
   "R": 0.3,
   "S": 0.2
  },
  "subjects": {
   "biology": 0.4,
   "chemistry": 0.3,
   "geography": 0.3
  },
  "values": {
   "balance": 0.1,
   "independence": 0.2,
   "learning": 0.3,
   "meaning": 0.4
  }
 },
 "event_manager": {
  "education": "either",
  "family": "hospitality",
  "riasec": {
   "A": 0.3,
   "E": 0.45,
   "S": 0.25
  },
  "subjects": {
   "art": 0.3,
   "economics": 0.3,
   "english": 0.4
  },
  "values": {
   "creativity": 0.3,
   "income": 0.15,
   "leadership": 0.25,
   "teamwork": 0.3
  }
 },
 "farm_manager": {
  "education": "either",
  "family": "agriculture",
  "riasec": {
   "C": 0.2,
   "E": 0.35,
   "R": 0.45
  },
  "subjects": {
   "biology": 0.4,
   "chemistry": 0.3,
   "geography": 0.3
  },
  "values": {
   "balance": 0.2,
   "income": 0.25,
   "independence": 0.35,
   "stability": 0.2
  }
 },
 "fashion_designer": {
  "education": "either",
  "family": "arts",
  "riasec": {
   "A": 0.75,
   "E": 0.15,
   "R": 0.1
  },
  "subjects": {
   "art": 0.7,
   "economics": 0.15,
   "literature": 0.15
  },
  "values": {
   "creativity": 0.5,
   "income": 0.15,
   "independence": 0.25,
   "leadership": 0.1
  }
 },
 "financial_analyst": {
  "education": "higher",
  "family": "finance",
  "riasec": {
   "C": 0.4,
   "E": 0.1,
   "I": 0.5
  },
  "subjects": {
   "cs": 0.1,
   "economics": 0.4,
   "math": 0.5
  },
  "values": {
   "income": 0.35,
   "independence": 0.15,
   "learning": 0.3,
   "stability": 0.2
  }
 },
 "fitness_trainer": {
  "education": "college",
  "family": "sport",
  "riasec": {
   "E": 0.2,
   "R": 0.4,
   "S": 0.4
  },
  "subjects": {
   "biology": 0.7,
   "english": 0.2,
   "geography": 0.1
  },
  "values": {
   "balance": 0.2,
   "helping": 0.3,
   "income": 0.2,
   "independence": 0.3
  }
 },
 "food_technologist": {
  "education": "higher",
  "family": "agriculture",
  "riasec": {
   "C": 0.2,
   "I": 0.45,
   "R": 0.35
  },
  "subjects": {
   "biology": 0.4,
   "chemistry": 0.5,
   "geography": 0.1
  },
  "values": {
   "income": 0.2,
   "learning": 0.3,
   "meaning": 0.2,
   "stability": 0.3
  }
 },
 "frontend_developer": {
  "education": "either",
  "family": "cs",
  "riasec": {
   "A": 0.4,
   "I": 0.4,
   "R": 0.2
  },
  "subjects": {
   "art": 0.3,
   "cs": 0.5,
   "math": 0.2
  },
  "values": {
   "creativity": 0.4,
   "income": 0.15,
   "independence": 0.2,
   "learning": 0.25
  }
 },
 "geneticist": {
  "education": "higher",
  "family": "science",
  "riasec": {
   "C": 0.15,
   "I": 0.75,
   "S": 0.1
  },
  "subjects": {
   "biology": 0.6,
   "chemistry": 0.3,
   "math": 0.1
  },
  "values": {
   "independence": 0.25,
   "learning": 0.45,
   "meaning": 0.3
  }
 },
 "graphic_designer": {
  "education": "either",
  "family": "arts",
  "riasec": {
   "A": 0.7,
   "E": 0.1,
   "R": 0.2
  },
  "subjects": {
   "art": 0.7,
   "cs": 0.15,
   "literature": 0.15
  },
  "values": {
   "creativity": 0.5,
   "income": 0.15,
   "independence": 0.25,
   "teamwork": 0.1
  }
 },
 "hotel_manager": {
  "education": "either",
  "family": "hospitality",
  "riasec": {
   "C": 0.2,
   "E": 0.45,
   "S": 0.35
  },
  "subjects": {
   "economics": 0.3,
   "english": 0.5,
   "geography": 0.2
  },
  "values": {
   "helping": 0.2,
   "income": 0.2,
   "leadership": 0.3,
   "teamwork": 0.3
  }
 },
 "hr_specialist": {
  "education": "either",
  "family": "psychology",
  "riasec": {
   "C": 0.2,
   "E": 0.35,
   "S": 0.45
  },
  "subjects": {
   "economics": 0.35,
   "history": 0.3,
   "literature": 0.35
  },
  "values": {
   "helping": 0.3,
   "leadership": 0.2,
   "stability": 0.2,
   "teamwork": 0.3
  }
 },
 "industrial_designer": {
  "education": "higher",
  "family": "architecture",
  "riasec": {
   "A": 0.5,
   "I": 0.2,
   "R": 0.3
  },
  "subjects": {
   "art": 0.4,
   "math": 0.3,
   "physics": 0.3
  },
  "values": {
   "creativity": 0.45,
   "income": 0.2,
   "independence": 0.25,
   "learning": 0.1
  }
 },
 "industrial_engineer": {
  "education": "higher",
  "family": "engineering",
  "riasec": {
   "C": 0.4,
   "E": 0.3,
   "R": 0.3
  },
  "subjects": {
   "cs": 0.2,
   "math": 0.4,
   "physics": 0.4
  },
  "values": {
   "balance": 0.2,
   "income": 0.25,
   "stability": 0.3,
   "teamwork": 0.25
  }
 },
 "interior_designer": {
  "education": "either",
  "family": "architecture",
  "riasec": {
   "A": 0.7,
   "E": 0.1,
   "R": 0.2
  },
  "subjects": {
   "art": 0.6,
   "math": 0.2,
   "physics": 0.2
  },
  "values": {
   "creativity": 0.5,
   "income": 0.2,
   "independence": 0.3
  }
 },
 "investment_analyst": {
  "education": "higher",
  "family": "finance",
  "riasec": {
   "C": 0.2,
   "E": 0.3,
   "I": 0.5
  },
  "subjects": {
   "cs": 0.1,
   "economics": 0.4,
   "math": 0.5
  },
  "values": {
   "income": 0.45,
   "independence": 0.2,
   "leadership": 0.1,
   "learning": 0.25
  }
 },
 "journalist": {
  "education": "either",
  "family": "media",
  "riasec": {
   "A": 0.4,
   "E": 0.35,
   "S": 0.25
  },
  "subjects": {
   "english": 0.3,
   "history": 0.2,
   "literature": 0.5
  },
  "values": {
   "creativity": 0.3,
   "independence": 0.25,
   "learning": 0.15,
   "meaning": 0.3
  }
 },
 "judge": {
  "education": "higher",
  "family": "law",
  "riasec": {
   "C": 0.45,
   "E": 0.25,
   "S": 0.3
  },
  "subjects": {
   "economics": 0.25,
   "history": 0.4,
   "literature": 0.35
  },
  "values": {
   "income": 0.15,
   "leadership": 0.2,
   "meaning": 0.35,
   "stability": 0.3
  }
 },
 "lab_technician": {
  "education": "college",
  "family": "medicine",
  "riasec": {
   "C": 0.4,
   "I": 0.5,
   "R": 0.1
  },
  "subjects": {
   "biology": 0.4,
   "chemistry": 0.5,
   "math": 0.1
  },
  "values": {
   "balance": 0.2,
   "learning": 0.25,
   "meaning": 0.2,
   "stability": 0.35
  }
 },
 "landscape_designer": {
  "education": "either",
  "family": "architecture",
  "riasec": {
   "A": 0.6,
   "I": 0.1,
   "R": 0.3
  },
  "subjects": {
   "art": 0.4,
   "biology": 0.3,
   "geography": 0.3
  },
  "values": {
   "balance": 0.15,
   "creativity": 0.45,
   "independence": 0.25,
   "meaning": 0.15
  }
 },
 "lawyer": {
  "education": "higher",
  "family": "law",
  "riasec": {
   "C": 0.3,
   "E": 0.4,
   "S": 0.3
  },
  "subjects": {
   "economics": 0.3,
   "history": 0.4,
   "literature": 0.3
  },
  "values": {
   "income": 0.3,
   "independence": 0.2,
   "leadership": 0.25,
   "meaning": 0.25
  }
 },
 "legal_advisor": {
  "education": "either",
  "family": "law",
  "riasec": {
   "C": 0.45,
   "E": 0.3,
   "I": 0.25
  },
  "subjects": {
   "economics": 0.35,
   "history": 0.35,
   "literature": 0.3
  },
  "values": {
   "balance": 0.2,
   "income": 0.3,
   "independence": 0.15,
   "stability": 0.35
  }
 },
 "logistician": {
  "education": "either",
  "family": "logistics",
  "riasec": {
   "C": 0.45,
   "E": 0.25,
   "R": 0.3
  },
  "subjects": {
   "geography": 0.4,
   "math": 0.4,
   "physics": 0.2
  },
  "values": {
   "balance": 0.2,
   "income": 0.25,
   "stability": 0.35,
   "teamwork": 0.2
  }
 },
 "marketing_manager": {
  "education": "either",
  "family": "business",
  "riasec": {
   "A": 0.3,
   "E": 0.5,
   "S": 0.2
  },
  "subjects": {
   "economics": 0.4,
   "english": 0.3,
   "math": 0.3
  },
  "values": {
   "creativity": 0.35,
   "income": 0.2,
   "leadership": 0.25,
   "teamwork": 0.2
  }
 },
 "mechanical_engineer": {
  "education": "higher",
  "family": "engineering",
  "riasec": {
   "C": 0.1,
   "I": 0.4,
   "R": 0.5
  },
  "subjects": {
   "cs": 0.2,
   "math": 0.4,
   "physics": 0.4
  },
  "values": {
   "income": 0.25,
   "learning": 0.3,
   "stability": 0.25,
   "teamwork": 0.2
  }
 },
 "methodologist": {
  "education": "higher",
  "family": "education",
  "riasec": {
   "C": 0.4,
   "I": 0.25,
   "S": 0.35
  },
  "subjects": {
   "english": 0.3,
   "history": 0.3,
   "literature": 0.4
  },
  "values": {
   "balance": 0.15,
   "learning": 0.25,
   "meaning": 0.3,
   "stability": 0.3
  }
 },
 "mobile_developer": {
  "education": "either",
  "family": "cs",
  "riasec": {
   "A": 0.3,
   "I": 0.4,
   "R": 0.3
  },
  "subjects": {
   "cs": 0.4,
   "math": 0.4,
   "physics": 0.2
  },
  "values": {
   "creativity": 0.35,
   "income": 0.15,
   "independence": 0.2,
   "learning": 0.3
  }
 },
 "musician": {
  "education": "either",
  "family": "arts",
  "riasec": {
   "A": 0.85,
   "E": 0.05,
   "S": 0.1
  },
  "subjects": {
   "art": 0.7,
   "literature": 0.3
  },
  "values": {
   "creativity": 0.55,
   "independence": 0.3,
   "meaning": 0.15
  }
 },
 "notary": {
  "education": "higher",
  "family": "law",
  "riasec": {
   "C": 0.7,
   "E": 0.1,
   "S": 0.2
  },
  "subjects": {
   "economics": 0.3,
   "history": 0.4,
   "literature": 0.3
  },
  "values": {
   "balance": 0.2,
   "income": 0.25,
   "independence": 0.15,
   "stability": 0.4
  }
 },
 "nurse": {
  "education": "college",
  "family": "medicine",
  "riasec": {
   "C": 0.2,
   "R": 0.2,
   "S": 0.6
  },
  "subjects": {
   "biology": 0.5,
   "chemistry": 0.4,
   "physics": 0.1
  },
  "values": {
   "helping": 0.45,
   "meaning": 0.25,
   "stability": 0.1,
   "teamwork": 0.2
  }
 },
 "operations_manager": {
  "education": "either",
  "family": "business",
  "riasec": {
   "C": 0.5,
   "E": 0.3,
   "R": 0.2
  },
  "subjects": {
   "economics": 0.4,
   "english": 0.3,
   "math": 0.3
  },
  "values": {
   "income": 0.2,
   "leadership": 0.3,
   "stability": 0.3,
   "teamwork": 0.2
  }
 },
 "paramedic": {
  "education": "college",
  "family": "medicine",
  "riasec": {
   "C": 0.2,
   "R": 0.4,
   "S": 0.4
  },
  "subjects": {
   "biology": 0.5,
   "chemistry": 0.4,
   "physics": 0.1
  },
  "values": {
   "helping": 0.4,
   "meaning": 0.3,
   "stability": 0.1,
   "teamwork": 0.2
  }
 },
 "pe_teacher": {
  "education": "higher",
  "family": "sport",
  "riasec": {
   "E": 0.15,
   "R": 0.35,
   "S": 0.5
  },
  "subjects": {
   "biology": 0.6,
   "english": 0.2,
   "geography": 0.2
  },
  "values": {
   "balance": 0.25,
   "helping": 0.35,
   "meaning": 0.25,
   "stability": 0.15
  }
 },
 "pharmacist": {
  "education": "higher",
  "family": "medicine",
  "riasec": {
   "C": 0.4,
   "I": 0.4,
   "S": 0.2
  },
  "subjects": {
   "biology": 0.4,
   "chemistry": 0.5,
   "math": 0.1
  },
  "values": {
   "balance": 0.15,
   "helping": 0.3,
   "learning": 0.2,
   "stability": 0.35
  }
 },
 "photographer": {
  "education": "either",
  "family": "media",
  "riasec": {
   "A": 0.7,
   "E": 0.1,
   "R": 0.2
  },
  "subjects": {
   "art": 0.6,
   "literature": 0.2,
   "physics": 0.2
  },
  "values": {
   "balance": 0.1,
   "creativity": 0.5,
   "income": 0.1,
   "independence": 0.3
  }
 },
 "physicist": {
  "education": "higher",
  "family": "science",
  "riasec": {
   "A": 0.1,
   "I": 0.8,
   "R": 0.1
  },
  "subjects": {
   "math": 0.5,
   "physics": 0.5
  },
  "values": {
   "independence": 0.3,
   "learning": 0.5,
   "meaning": 0.2
  }
 },
 "physiotherapist": {
  "education": "higher",
  "family": "sport",
  "riasec": {
   "I": 0.25,
   "R": 0.3,
   "S": 0.45
  },
  "subjects": {
   "biology": 0.7,
   "english": 0.2,
   "geography": 0.1
  },
  "values": {
   "balance": 0.15,
   "helping": 0.4,
   "meaning": 0.25,
   "stability": 0.2
  }
 },
 "primary_teacher": {
  "education": "either",
  "family": "education",
  "riasec": {
   "A": 0.15,
   "C": 0.1,
   "S": 0.75
  },
  "subjects": {
   "english": 0.3,
   "history": 0.3,
   "literature": 0.4
  },
  "values": {
   "balance": 0.2,
   "helping": 0.4,
   "meaning": 0.3,
   "stability": 0.1
  }
 },
 "product_manager": {
  "education": "higher",
  "family": "business",
  "riasec": {
   "E": 0.4,
   "I": 0.3,
   "S": 0.3
  },
  "subjects": {
   "economics": 0.4,
   "english": 0.3,
   "math": 0.3
  },
  "values": {
   "creativity": 0.2,
   "leadership": 0.3,
   "learning": 0.25,
   "teamwork": 0.25
  }
 },
 "prosecutor": {
  "education": "higher",
  "family": "law",
  "riasec": {
   "C": 0.35,
   "E": 0.45,
   "S": 0.2
  },
  "subjects": {
   "economics": 0.3,
   "history": 0.4,
   "literature": 0.3
  },
  "values": {
   "income": 0.15,
   "leadership": 0.25,
   "meaning": 0.35,
   "stability": 0.25
  }
 },
 "psychologist": {
  "education": "higher",
  "family": "psychology",
  "riasec": {
   "A": 0.1,
   "I": 0.3,
   "S": 0.6
  },
  "subjects": {
   "biology": 0.4,
   "history": 0.3,
   "literature": 0.3
  },
  "values": {
   "helping": 0.45,
   "learning": 0.25,
   "meaning": 0.3
  }
 },
 "researcher": {
  "education": "higher",
  "family": "science",
  "riasec": {
   "A": 0.2,
   "C": 0.1,
   "I": 0.7
  },
  "subjects": {
   "biology": 0.2,
   "chemistry": 0.3,
   "math": 0.2,
   "physics": 0.3
  },
  "values": {
   "independence": 0.3,
   "learning": 0.45,
   "meaning": 0.25
  }
 },
 "restaurant_manager": {
  "education": "either",
  "family": "hospitality",
  "riasec": {
   "C": 0.3,
   "E": 0.45,
   "S": 0.25
  },
  "subjects": {
   "economics": 0.4,
   "english": 0.3,
   "geography": 0.3
  },
  "values": {
   "income": 0.3,
   "leadership": 0.3,
   "stability": 0.15,
   "teamwork": 0.25
  }
 },
 "robotics_engineer": {
  "education": "higher",
  "family": "engineering",
  "riasec": {
   "A": 0.1,
   "I": 0.5,
   "R": 0.4
  },
  "subjects": {
   "cs": 0.4,
   "math": 0.2,
   "physics": 0.4
  },
  "values": {
   "creativity": 0.25,
   "income": 0.15,
   "independence": 0.2,
   "learning": 0.4
  }
 },
 "sales_manager": {
  "education": "either",
  "family": "business",
  "riasec": {
   "C": 0.1,
   "E": 0.6,
   "S": 0.3
  },
  "subjects": {
   "economics": 0.4,
   "english": 0.3,
   "math": 0.3
  },
  "values": {
   "income": 0.4,
   "independence": 0.15,
   "leadership": 0.2,
   "teamwork": 0.25
  }
 },
 "school_counselor": {
  "education": "higher",
  "family": "psychology",
  "riasec": {
   "C": 0.1,
   "I": 0.2,
   "S": 0.7
  },
  "subjects": {
   "biology": 0.4,
   "history": 0.3,
   "literature": 0.3
  },
  "values": {
   "balance": 0.15,
   "helping": 0.45,
   "meaning": 0.3,
   "teamwork": 0.1
  }
 },
 "school_principal": {
  "education": "higher",
  "family": "education",
  "riasec": {
   "C": 0.2,
   "E": 0.4,
   "S": 0.4
  },
  "subjects": {
   "english": 0.3,
   "history": 0.3,
   "literature": 0.4
  },
  "values": {
   "helping": 0.2,
   "leadership": 0.35,
   "meaning": 0.25,
   "stability": 0.2
  }
 },
 "smm_specialist": {
  "education": "either",
  "family": "media",
  "riasec": {
   "A": 0.4,
   "C": 0.2,
   "E": 0.4
  },
  "subjects": {
   "art": 0.2,
   "english": 0.4,
   "literature": 0.4
  },
  "values": {
   "creativity": 0.4,
   "income": 0.2,
   "independence": 0.25,
   "teamwork": 0.15
  }
 },
 "social_worker": {
  "education": "either",
  "family": "psychology",
  "riasec": {
   "C": 0.15,
   "I": 0.1,
   "S": 0.75
  },
  "subjects": {
   "biology": 0.4,
   "history": 0.3,
   "literature": 0.3
  },
  "values": {
   "helping": 0.5,
   "meaning": 0.35,
   "teamwork": 0.15
  }
 },
 "software_engineer": {
  "education": "either",
  "family": "cs",
  "riasec": {
   "C": 0.2,
   "I": 0.5,
   "R": 0.3
  },
  "subjects": {
   "cs": 0.4,
   "math": 0.4,
   "physics": 0.2
  },
  "values": {
   "creativity": 0.2,
   "income": 0.2,
   "independence": 0.25,
   "learning": 0.35
  }
 },
 "speech_therapist": {
  "education": "higher",
  "family": "psychology",
  "riasec": {
   "C": 0.15,
   "I": 0.2,
   "S": 0.65
  },
  "subjects": {
   "biology": 0.4,
   "history": 0.2,
   "literature": 0.4
  },
  "values": {
   "balance": 0.15,
   "helping": 0.45,
   "meaning": 0.3,
   "stability": 0.1
  }
 },
 "sports_manager": {
  "education": "higher",
  "family": "sport",
  "riasec": {
   "C": 0.3,
   "E": 0.5,
   "S": 0.2
  },
  "subjects": {
   "biology": 0.3,
   "economics": 0.4,
   "english": 0.3
  },
  "values": {
   "balance": 0.15,
   "income": 0.3,
   "leadership": 0.3,
   "teamwork": 0.25
  }
 },
 "supply_chain_manager": {
  "education": "higher",
  "family": "logistics",
  "riasec": {
   "C": 0.4,
   "E": 0.35,
   "R": 0.25
  },
  "subjects": {
   "economics": 0.3,
   "geography": 0.3,
   "math": 0.4
  },
  "values": {
   "income": 0.25,
   "leadership": 0.3,
   "stability": 0.3,
   "teamwork": 0.15
  }
 },
 "surgeon": {
  "education": "higher",
  "family": "medicine",
  "riasec": {
   "I": 0.35,
   "R": 0.4,
   "S": 0.25
  },
  "subjects": {
   "biology": 0.5,
   "chemistry": 0.3,
   "physics": 0.2
  },
  "values": {
   "helping": 0.35,
   "income": 0.15,
   "learning": 0.25,
   "meaning": 0.25
  }
 },
 "surveyor": {
  "education": "college",
  "family": "logistics",
  "riasec": {
   "C": 0.35,
   "I": 0.2,
   "R": 0.45
  },
  "subjects": {
   "geography": 0.4,
   "math": 0.4,
   "physics": 0.2
  },
  "values": {
   "balance": 0.2,
   "income": 0.2,
   "independence": 0.25,
   "stability": 0.35
  }
 },
 "systems_analyst": {
  "education": "higher",
  "family": "cs",
  "riasec": {
   "C": 0.4,
   "E": 0.2,
   "I": 0.4
  },
  "subjects": {
   "cs": 0.4,
   "math": 0.4,
   "physics": 0.2
  },
  "values": {
   "income": 0.2,
   "learning": 0.3,
   "stability": 0.25,
   "teamwork": 0.25
  }
 },
 "tax_specialist": {
  "education": "either",
  "family": "finance",
  "riasec": {
   "C": 0.7,
   "E": 0.2,
   "I": 0.1
  },
  "subjects": {
   "cs": 0.1,
   "economics": 0.4,
   "math": 0.5
  },
  "values": {
   "balance": 0.2,
   "income": 0.25,
   "meaning": 0.15,
   "stability": 0.4
  }
 },
 "teacher": {
  "education": "higher",
  "family": "education",
  "riasec": {
   "A": 0.2,
   "C": 0.1,
   "S": 0.7
  },
  "subjects": {
   "english": 0.3,
   "history": 0.3,
   "literature": 0.4
  },
  "values": {
   "balance": 0.2,
   "helping": 0.35,
   "meaning": 0.3,
   "stability": 0.15
  }
 },
 "technician": {
  "education": "college",
  "family": "engineering",
  "riasec": {
   "C": 0.3,
   "R": 0.7
  },
  "subjects": {
   "cs": 0.2,
   "math": 0.4,
   "physics": 0.4
  },
  "values": {
   "balance": 0.2,
   "income": 0.25,
   "stability": 0.35,
   "teamwork": 0.2
  }
 },
 "therapist": {
  "education": "higher",
  "family": "psychology",
  "riasec": {
   "A": 0.1,
   "I": 0.25,
   "S": 0.65
  },
  "subjects": {
   "biology": 0.4,
   "history": 0.25,
   "literature": 0.35
  },
  "values": {
   "balance": 0.1,
   "helping": 0.45,
   "independence": 0.15,
   "meaning": 0.3
  }
 },
 "tour_guide": {
  "education": "either",
  "family": "hospitality",
  "riasec": {
   "A": 0.2,
   "E": 0.35,
   "S": 0.45
  },
  "subjects": {
   "english": 0.4,
   "geography": 0.4,
   "history": 0.2
  },
  "values": {
   "balance": 0.2,
   "helping": 0.25,
   "independence": 0.25,
   "teamwork": 0.3
  }
 },
 "travel_agent": {
  "education": "either",
  "family": "hospitality",
  "riasec": {
   "C": 0.25,
   "E": 0.4,
   "S": 0.35
  },
  "subjects": {
   "economics": 0.1,
   "english": 0.5,
   "geography": 0.4
  },
  "values": {
   "balance": 0.2,
   "helping": 0.25,
   "income": 0.25,
   "teamwork": 0.3
  }
 },
 "tutor": {
  "education": "either",
  "family": "education",
  "riasec": {
   "E": 0.15,
   "I": 0.25,
   "S": 0.6
  },
  "subjects": {
   "english": 0.3,
   "history": 0.3,
   "literature": 0.4
  },
  "values": {
   "balance": 0.2,
   "helping": 0.3,
   "income": 0.2,
   "independence": 0.3
  }
 },
 "tv_producer": {
  "education": "higher",
  "family": "media",
  "riasec": {
   "A": 0.4,
   "C": 0.2,
   "E": 0.4
  },
  "subjects": {
   "art": 0.3,
   "english": 0.3,
   "literature": 0.4
  },
  "values": {
   "creativity": 0.35,
   "income": 0.15,
   "leadership": 0.3,
   "teamwork": 0.2
  }
 },
 "university_lecturer": {
  "education": "higher",
  "family": "education",
  "riasec": {
   "A": 0.1,
   "I": 0.45,
   "S": 0.45
  },
  "subjects": {
   "english": 0.3,
   "history": 0.3,
   "literature": 0.4
  },
  "values": {
   "helping": 0.15,
   "independence": 0.2,
   "learning": 0.4,
   "meaning": 0.25
  }
 },
 "urban_planner": {
  "education": "higher",
  "family": "architecture",
  "riasec": {
   "A": 0.3,
   "C": 0.3,
   "I": 0.4
  },
  "subjects": {
   "art": 0.3,
   "geography": 0.4,
   "math": 0.3
  },
  "values": {
   "creativity": 0.25,
   "leadership": 0.2,
   "meaning": 0.35,
   "stability": 0.2
  }
 },
 "veterinarian": {
  "education": "higher",
  "family": "agriculture",
  "riasec": {
   "I": 0.35,
   "R": 0.35,
   "S": 0.3
  },
  "subjects": {
   "biology": 0.6,
   "chemistry": 0.3,
   "geography": 0.1
  },
  "values": {
   "helping": 0.35,
   "independence": 0.2,
   "learning": 0.2,
   "meaning": 0.25
  }
 },
 "warehouse_manager": {
  "education": "college",
  "family": "logistics",
  "riasec": {
   "C": 0.5,
   "E": 0.2,
   "R": 0.3
  },
  "subjects": {
   "geography": 0.3,
   "math": 0.5,
   "physics": 0.2
  },
  "values": {
   "balance": 0.15,
   "income": 0.25,
   "stability": 0.4,
   "teamwork": 0.2
  }
 }
}

export const MAJOR_ENTRIES = {
 "major_accounting": {
  "education": "higher",
  "family": "finance",
  "riasec": {
   "C": 0.7,
   "E": 0.1,
   "I": 0.2
  },
  "subjects": {
   "cs": 0.1,
   "economics": 0.4,
   "math": 0.5
  },
  "values": {
   "balance": 0.2,
   "income": 0.3,
   "stability": 0.4,
   "teamwork": 0.1
  }
 },
 "major_agronomy": {
  "education": "higher",
  "family": "agriculture",
  "riasec": {
   "C": 0.15,
   "I": 0.35,
   "R": 0.5
  },
  "subjects": {
   "biology": 0.5,
   "chemistry": 0.3,
   "geography": 0.2
  },
  "values": {
   "balance": 0.2,
   "independence": 0.25,
   "meaning": 0.3,
   "stability": 0.25
  }
 },
 "major_architecture": {
  "education": "higher",
  "family": "architecture",
  "riasec": {
   "A": 0.5,
   "I": 0.2,
   "R": 0.3
  },
  "subjects": {
   "art": 0.4,
   "math": 0.3,
   "physics": 0.3
  },
  "values": {
   "creativity": 0.45,
   "income": 0.15,
   "independence": 0.25,
   "meaning": 0.15
  }
 },
 "major_banking": {
  "education": "higher",
  "family": "finance",
  "riasec": {
   "C": 0.4,
   "E": 0.4,
   "I": 0.2
  },
  "subjects": {
   "cs": 0.1,
   "economics": 0.4,
   "math": 0.5
  },
  "values": {
   "income": 0.35,
   "leadership": 0.1,
   "stability": 0.35,
   "teamwork": 0.2
  }
 },
 "major_biology": {
  "education": "higher",
  "family": "science",
  "riasec": {
   "I": 0.7,
   "R": 0.2,
   "S": 0.1
  },
  "subjects": {
   "biology": 0.6,
   "chemistry": 0.3,
   "math": 0.1
  },
  "values": {
   "independence": 0.3,
   "learning": 0.4,
   "meaning": 0.3
  }
 },
 "major_biotechnology": {
  "education": "higher",
  "family": "science",
  "riasec": {
   "C": 0.15,
   "I": 0.65,
   "R": 0.2
  },
  "subjects": {
   "biology": 0.5,
   "chemistry": 0.4,
   "math": 0.1
  },
  "values": {
   "income": 0.15,
   "independence": 0.15,
   "learning": 0.4,
   "meaning": 0.3
  }
 },
 "major_business_admin": {
  "education": "higher",
  "family": "business",
  "riasec": {
   "C": 0.3,
   "E": 0.5,
   "S": 0.2
  },
  "subjects": {
   "economics": 0.4,
   "english": 0.3,
   "math": 0.3
  },
  "values": {
   "income": 0.3,
   "leadership": 0.3,
   "stability": 0.2,
   "teamwork": 0.2
  }
 },
 "major_chemistry": {
  "education": "higher",
  "family": "science",
  "riasec": {
   "C": 0.1,
   "I": 0.7,
   "R": 0.2
  },
  "subjects": {
   "chemistry": 0.6,
   "math": 0.2,
   "physics": 0.2
  },
  "values": {
   "income": 0.1,
   "independence": 0.3,
   "learning": 0.4,
   "meaning": 0.2
  }
 },
 "major_civil_eng": {
  "education": "higher",
  "family": "engineering",
  "riasec": {
   "C": 0.3,
   "I": 0.2,
   "R": 0.5
  },
  "subjects": {
   "cs": 0.2,
   "math": 0.4,
   "physics": 0.4
  },
  "values": {
   "income": 0.25,
   "meaning": 0.2,
   "stability": 0.3,
   "teamwork": 0.25
  }
 },
 "major_construction_management": {
  "education": "higher",
  "family": "logistics",
  "riasec": {
   "C": 0.3,
   "E": 0.35,
   "R": 0.35
  },
  "subjects": {
   "geography": 0.2,
   "math": 0.4,
   "physics": 0.4
  },
  "values": {
   "income": 0.3,
   "leadership": 0.3,
   "stability": 0.2,
   "teamwork": 0.2
  }
 },
 "major_cs": {
  "education": "higher",
  "family": "cs",
  "riasec": {
   "C": 0.2,
   "I": 0.5,
   "R": 0.3
  },
  "subjects": {
   "cs": 0.4,
   "math": 0.4,
   "physics": 0.2
  },
  "values": {
   "creativity": 0.15,
   "income": 0.2,
   "independence": 0.25,
   "learning": 0.4
  }
 },
 "major_culinary": {
  "education": "either",
  "family": "hospitality",
  "riasec": {
   "A": 0.4,
   "E": 0.2,
   "R": 0.4
  },
  "subjects": {
   "biology": 0.3,
   "chemistry": 0.4,
   "economics": 0.3
  },
  "values": {
   "creativity": 0.4,
   "income": 0.2,
   "independence": 0.15,
   "teamwork": 0.25
  }
 },
 "major_data_science": {
  "education": "higher",
  "family": "cs",
  "riasec": {
   "A": 0.1,
   "C": 0.3,
   "I": 0.6
  },
  "subjects": {
   "cs": 0.3,
   "economics": 0.2,
   "math": 0.5
  },
  "values": {
   "income": 0.25,
   "independence": 0.3,
   "learning": 0.45
  }
 },
 "major_dentistry": {
  "education": "higher",
  "family": "medicine",
  "riasec": {
   "I": 0.25,
   "R": 0.4,
   "S": 0.35
  },
  "subjects": {
   "biology": 0.5,
   "chemistry": 0.4,
   "physics": 0.1
  },
  "values": {
   "helping": 0.3,
   "income": 0.3,
   "independence": 0.2,
   "stability": 0.2
  }
 },
 "major_ecology": {
  "education": "higher",
  "family": "agriculture",
  "riasec": {
   "I": 0.45,
   "R": 0.3,
   "S": 0.25
  },
  "subjects": {
   "biology": 0.5,
   "chemistry": 0.2,
   "geography": 0.3
  },
  "values": {
   "balance": 0.1,
   "independence": 0.25,
   "learning": 0.2,
   "meaning": 0.45
  }
 },
 "major_economics": {
  "education": "higher",
  "family": "finance",
  "riasec": {
   "C": 0.3,
   "E": 0.2,
   "I": 0.5
  },
  "subjects": {
   "economics": 0.4,
   "geography": 0.1,
   "math": 0.5
  },
  "values": {
   "income": 0.3,
   "independence": 0.15,
   "learning": 0.35,
   "meaning": 0.2
  }
 },
 "major_electrical_eng": {
  "education": "higher",
  "family": "engineering",
  "riasec": {
   "C": 0.1,
   "I": 0.5,
   "R": 0.4
  },
  "subjects": {
   "cs": 0.2,
   "math": 0.4,
   "physics": 0.4
  },
  "values": {
   "income": 0.25,
   "learning": 0.35,
   "stability": 0.25,
   "teamwork": 0.15
  }
 },
 "major_finance": {
  "education": "higher",
  "family": "finance",
  "riasec": {
   "C": 0.5,
   "E": 0.2,
   "I": 0.3
  },
  "subjects": {
   "cs": 0.1,
   "economics": 0.4,
   "math": 0.5
  },
  "values": {
   "income": 0.4,
   "independence": 0.1,
   "learning": 0.2,
   "stability": 0.3
  }
 },
 "major_fine_arts": {
  "education": "higher",
  "family": "arts",
  "riasec": {
   "A": 0.85,
   "E": 0.05,
   "I": 0.1
  },
  "subjects": {
   "art": 0.8,
   "literature": 0.2
  },
  "values": {
   "creativity": 0.55,
   "independence": 0.3,
   "meaning": 0.15
  }
 },
 "major_food_technology": {
  "education": "higher",
  "family": "agriculture",
  "riasec": {
   "C": 0.2,
   "I": 0.45,
   "R": 0.35
  },
  "subjects": {
   "biology": 0.4,
   "chemistry": 0.5,
   "geography": 0.1
  },
  "values": {
   "income": 0.2,
   "learning": 0.3,
   "meaning": 0.2,
   "stability": 0.3
  }
 },
 "major_graphic_design": {
  "education": "higher",
  "family": "arts",
  "riasec": {
   "A": 0.7,
   "E": 0.1,
   "R": 0.2
  },
  "subjects": {
   "art": 0.7,
   "cs": 0.15,
   "literature": 0.15
  },
  "values": {
   "creativity": 0.5,
   "income": 0.15,
   "independence": 0.25,
   "teamwork": 0.1
  }
 },
 "major_hotel_management": {
  "education": "higher",
  "family": "hospitality",
  "riasec": {
   "C": 0.2,
   "E": 0.45,
   "S": 0.35
  },
  "subjects": {
   "economics": 0.3,
   "english": 0.5,
   "geography": 0.2
  },
  "values": {
   "helping": 0.2,
   "income": 0.2,
   "leadership": 0.3,
   "teamwork": 0.3
  }
 },
 "major_info_security": {
  "education": "higher",
  "family": "cs",
  "riasec": {
   "C": 0.4,
   "I": 0.5,
   "R": 0.1
  },
  "subjects": {
   "cs": 0.4,
   "math": 0.4,
   "physics": 0.2
  },
  "values": {
   "income": 0.25,
   "learning": 0.3,
   "meaning": 0.15,
   "stability": 0.3
  }
 },
 "major_interior_design": {
  "education": "higher",
  "family": "architecture",
  "riasec": {
   "A": 0.7,
   "E": 0.1,
   "R": 0.2
  },
  "subjects": {
   "art": 0.6,
   "math": 0.2,
   "physics": 0.2
  },
  "values": {
   "creativity": 0.5,
   "income": 0.2,
   "independence": 0.3
  }
 },
 "major_international_relations": {
  "education": "higher",
  "family": "law",
  "riasec": {
   "E": 0.4,
   "I": 0.3,
   "S": 0.3
  },
  "subjects": {
   "english": 0.4,
   "history": 0.35,
   "literature": 0.25
  },
  "values": {
   "income": 0.2,
   "leadership": 0.2,
   "learning": 0.3,
   "meaning": 0.3
  }
 },
 "major_journalism": {
  "education": "higher",
  "family": "media",
  "riasec": {
   "A": 0.4,
   "E": 0.35,
   "S": 0.25
  },
  "subjects": {
   "english": 0.3,
   "history": 0.2,
   "literature": 0.5
  },
  "values": {
   "creativity": 0.3,
   "independence": 0.25,
   "learning": 0.15,
   "meaning": 0.3
  }
 },
 "major_law": {
  "education": "higher",
  "family": "law",
  "riasec": {
   "C": 0.35,
   "E": 0.4,
   "S": 0.25
  },
  "subjects": {
   "economics": 0.3,
   "history": 0.4,
   "literature": 0.3
  },
  "values": {
   "income": 0.3,
   "leadership": 0.25,
   "meaning": 0.3,
   "stability": 0.15
  }
 },
 "major_logistics": {
  "education": "higher",
  "family": "logistics",
  "riasec": {
   "C": 0.45,
   "E": 0.25,
   "R": 0.3
  },
  "subjects": {
   "geography": 0.4,
   "math": 0.4,
   "physics": 0.2
  },
  "values": {
   "balance": 0.2,
   "income": 0.25,
   "stability": 0.35,
   "teamwork": 0.2
  }
 },
 "major_management": {
  "education": "higher",
  "family": "business",
  "riasec": {
   "C": 0.2,
   "E": 0.6,
   "S": 0.2
  },
  "subjects": {
   "economics": 0.4,
   "english": 0.3,
   "math": 0.3
  },
  "values": {
   "income": 0.25,
   "independence": 0.2,
   "leadership": 0.35,
   "teamwork": 0.2
  }
 },
 "major_marketing": {
  "education": "higher",
  "family": "business",
  "riasec": {
   "A": 0.3,
   "E": 0.5,
   "S": 0.2
  },
  "subjects": {
   "economics": 0.4,
   "english": 0.3,
   "math": 0.3
  },
  "values": {
   "creativity": 0.35,
   "income": 0.2,
   "leadership": 0.25,
   "teamwork": 0.2
  }
 },
 "major_mechanical_eng": {
  "education": "higher",
  "family": "engineering",
  "riasec": {
   "C": 0.1,
   "I": 0.4,
   "R": 0.5
  },
  "subjects": {
   "cs": 0.2,
   "math": 0.4,
   "physics": 0.4
  },
  "values": {
   "income": 0.25,
   "learning": 0.3,
   "stability": 0.25,
   "teamwork": 0.2
  }
 },
 "major_mechatronics": {
  "education": "higher",
  "family": "engineering",
  "riasec": {
   "A": 0.1,
   "I": 0.5,
   "R": 0.4
  },
  "subjects": {
   "cs": 0.4,
   "math": 0.2,
   "physics": 0.4
  },
  "values": {
   "creativity": 0.25,
   "income": 0.15,
   "independence": 0.2,
   "learning": 0.4
  }
 },
 "major_media_communications": {
  "education": "higher",
  "family": "media",
  "riasec": {
   "A": 0.4,
   "E": 0.4,
   "S": 0.2
  },
  "subjects": {
   "art": 0.2,
   "english": 0.4,
   "literature": 0.4
  },
  "values": {
   "creativity": 0.35,
   "income": 0.2,
   "independence": 0.2,
   "teamwork": 0.25
  }
 },
 "major_medicine": {
  "education": "higher",
  "family": "medicine",
  "riasec": {
   "I": 0.4,
   "R": 0.2,
   "S": 0.4
  },
  "subjects": {
   "biology": 0.5,
   "chemistry": 0.4,
   "physics": 0.1
  },
  "values": {
   "helping": 0.4,
   "learning": 0.2,
   "meaning": 0.25,
   "stability": 0.15
  }
 },
 "major_music": {
  "education": "higher",
  "family": "arts",
  "riasec": {
   "A": 0.85,
   "E": 0.05,
   "S": 0.1
  },
  "subjects": {
   "art": 0.7,
   "literature": 0.3
  },
  "values": {
   "creativity": 0.55,
   "independence": 0.3,
   "meaning": 0.15
  }
 },
 "major_nursing": {
  "education": "either",
  "family": "medicine",
  "riasec": {
   "C": 0.2,
   "R": 0.2,
   "S": 0.6
  },
  "subjects": {
   "biology": 0.5,
   "chemistry": 0.4,
   "physics": 0.1
  },
  "values": {
   "helping": 0.45,
   "meaning": 0.25,
   "stability": 0.1,
   "teamwork": 0.2
  }
 },
 "major_pedagogy": {
  "education": "higher",
  "family": "education",
  "riasec": {
   "A": 0.2,
   "C": 0.1,
   "S": 0.7
  },
  "subjects": {
   "english": 0.3,
   "history": 0.3,
   "literature": 0.4
  },
  "values": {
   "balance": 0.2,
   "helping": 0.35,
   "meaning": 0.3,
   "stability": 0.15
  }
 },
 "major_pharmacy": {
  "education": "higher",
  "family": "medicine",
  "riasec": {
   "C": 0.4,
   "I": 0.4,
   "S": 0.2
  },
  "subjects": {
   "biology": 0.4,
   "chemistry": 0.5,
   "math": 0.1
  },
  "values": {
   "balance": 0.15,
   "helping": 0.3,
   "learning": 0.2,
   "stability": 0.35
  }
 },
 "major_philology": {
  "education": "higher",
  "family": "education",
  "riasec": {
   "A": 0.4,
   "I": 0.25,
   "S": 0.35
  },
  "subjects": {
   "english": 0.3,
   "history": 0.2,
   "literature": 0.5
  },
  "values": {
   "balance": 0.15,
   "creativity": 0.3,
   "learning": 0.35,
   "meaning": 0.2
  }
 },
 "major_physical_education": {
  "education": "higher",
  "family": "sport",
  "riasec": {
   "E": 0.15,
   "R": 0.35,
   "S": 0.5
  },
  "subjects": {
   "biology": 0.6,
   "english": 0.2,
   "geography": 0.2
  },
  "values": {
   "balance": 0.25,
   "helping": 0.35,
   "meaning": 0.25,
   "stability": 0.15
  }
 },
 "major_physics": {
  "education": "higher",
  "family": "science",
  "riasec": {
   "A": 0.1,
   "I": 0.8,
   "R": 0.1
  },
  "subjects": {
   "math": 0.5,
   "physics": 0.5
  },
  "values": {
   "independence": 0.3,
   "learning": 0.5,
   "meaning": 0.2
  }
 },
 "major_physiotherapy": {
  "education": "higher",
  "family": "sport",
  "riasec": {
   "I": 0.25,
   "R": 0.3,
   "S": 0.45
  },
  "subjects": {
   "biology": 0.7,
   "english": 0.2,
   "geography": 0.1
  },
  "values": {
   "balance": 0.15,
   "helping": 0.4,
   "meaning": 0.25,
   "stability": 0.2
  }
 },
 "major_political_science": {
  "education": "higher",
  "family": "law",
  "riasec": {
   "E": 0.35,
   "I": 0.4,
   "S": 0.25
  },
  "subjects": {
   "economics": 0.25,
   "history": 0.45,
   "literature": 0.3
  },
  "values": {
   "independence": 0.15,
   "leadership": 0.2,
   "learning": 0.3,
   "meaning": 0.35
  }
 },
 "major_pr": {
  "education": "higher",
  "family": "media",
  "riasec": {
   "A": 0.3,
   "E": 0.5,
   "S": 0.2
  },
  "subjects": {
   "economics": 0.2,
   "english": 0.4,
   "literature": 0.4
  },
  "values": {
   "creativity": 0.3,
   "income": 0.2,
   "leadership": 0.3,
   "teamwork": 0.2
  }
 },
 "major_primary_education": {
  "education": "higher",
  "family": "education",
  "riasec": {
   "A": 0.15,
   "C": 0.1,
   "S": 0.75
  },
  "subjects": {
   "english": 0.3,
   "history": 0.3,
   "literature": 0.4
  },
  "values": {
   "balance": 0.2,
   "helping": 0.4,
   "meaning": 0.3,
   "stability": 0.1
  }
 },
 "major_psychology": {
  "education": "higher",
  "family": "psychology",
  "riasec": {
   "A": 0.1,
   "I": 0.3,
   "S": 0.6
  },
  "subjects": {
   "biology": 0.4,
   "history": 0.3,
   "literature": 0.3
  },
  "values": {
   "helping": 0.45,
   "learning": 0.25,
   "meaning": 0.3
  }
 },
 "major_social_work": {
  "education": "higher",
  "family": "psychology",
  "riasec": {
   "C": 0.15,
   "I": 0.1,
   "S": 0.75
  },
  "subjects": {
   "biology": 0.4,
   "history": 0.3,
   "literature": 0.3
  },
  "values": {
   "helping": 0.5,
   "meaning": 0.35,
   "teamwork": 0.15
  }
 },
 "major_software_eng": {
  "education": "higher",
  "family": "cs",
  "riasec": {
   "C": 0.3,
   "I": 0.5,
   "R": 0.2
  },
  "subjects": {
   "cs": 0.4,
   "math": 0.4,
   "physics": 0.2
  },
  "values": {
   "creativity": 0.15,
   "income": 0.25,
   "independence": 0.25,
   "learning": 0.35
  }
 },
 "major_special_education": {
  "education": "higher",
  "family": "psychology",
  "riasec": {
   "A": 0.1,
   "I": 0.2,
   "S": 0.7
  },
  "subjects": {
   "biology": 0.35,
   "history": 0.3,
   "literature": 0.35
  },
  "values": {
   "balance": 0.2,
   "helping": 0.5,
   "meaning": 0.3
  }
 },
 "major_sports_science": {
  "education": "higher",
  "family": "sport",
  "riasec": {
   "I": 0.4,
   "R": 0.35,
   "S": 0.25
  },
  "subjects": {
   "biology": 0.7,
   "english": 0.2,
   "geography": 0.1
  },
  "values": {
   "balance": 0.15,
   "helping": 0.25,
   "learning": 0.35,
   "meaning": 0.25
  }
 },
 "major_theatre": {
  "education": "higher",
  "family": "arts",
  "riasec": {
   "A": 0.7,
   "E": 0.2,
   "S": 0.1
  },
  "subjects": {
   "art": 0.5,
   "literature": 0.5
  },
  "values": {
   "creativity": 0.5,
   "independence": 0.2,
   "meaning": 0.15,
   "teamwork": 0.15
  }
 },
 "major_tourism": {
  "education": "higher",
  "family": "hospitality",
  "riasec": {
   "C": 0.2,
   "E": 0.4,
   "S": 0.4
  },
  "subjects": {
   "economics": 0.2,
   "english": 0.5,
   "geography": 0.3
  },
  "values": {
   "balance": 0.2,
   "helping": 0.25,
   "income": 0.25,
   "teamwork": 0.3
  }
 },
 "major_transport": {
  "education": "higher",
  "family": "logistics",
  "riasec": {
   "C": 0.4,
   "E": 0.2,
   "R": 0.4
  },
  "subjects": {
   "geography": 0.3,
   "math": 0.4,
   "physics": 0.3
  },
  "values": {
   "balance": 0.15,
   "income": 0.3,
   "stability": 0.35,
   "teamwork": 0.2
  }
 },
 "major_urban_planning": {
  "education": "higher",
  "family": "architecture",
  "riasec": {
   "A": 0.3,
   "C": 0.3,
   "I": 0.4
  },
  "subjects": {
   "art": 0.3,
   "geography": 0.4,
   "math": 0.3
  },
  "values": {
   "creativity": 0.25,
   "leadership": 0.2,
   "meaning": 0.35,
   "stability": 0.2
  }
 },
 "major_veterinary": {
  "education": "higher",
  "family": "agriculture",
  "riasec": {
   "I": 0.35,
   "R": 0.35,
   "S": 0.3
  },
  "subjects": {
   "biology": 0.6,
   "chemistry": 0.3,
   "geography": 0.1
  },
  "values": {
   "helping": 0.35,
   "independence": 0.2,
   "learning": 0.2,
   "meaning": 0.25
  }
 }
}

export const SUBJECT_KEYS = ["math","physics","cs","biology","chemistry","economics","english","literature","history","geography","art"]

// The scorer wants {subject: {score 0..1, weight}}, NOT a raw 1..5. Naseeb Edu
// collects confidence, which TestMind already anticipated: it is worth 0.6 of a
// real mark, because how good a student feels at physics is weaker evidence
// than what they actually scored in it.
export const SUBJECT_SCALES = {
 "scales": {
  "confidence": {
   "max": 5,
   "min": 1
  },
  "mark_five": {
   "max": 5,
   "min": 2
  },
  "mark_hundred": {
   "max": 100,
   "min": 0
  }
 },
 "weights": {
  "confidence": 0.6,
  "mark_five": 1,
  "mark_hundred": 1
 }
}

// What each school subject implies about the six interest scales. Lifted from
// TestMind's own table so the two products read a maths-confident student the
// same way.
export const SUBJ_AFFINITY = {
  math: {I: .6, C: .4}, physics: {I: .6, R: .4}, cs: {I: .5, R: .3, C: .2},
  biology: {I: .7, S: .3}, chemistry: {I: .7, R: .3}, economics: {E: .5, C: .3, I: .2},
  english: {S: .4, A: .3, E: .3}, literature: {A: .6, S: .4},
  history: {I: .4, S: .3, A: .3}, geography: {I: .4, R: .3, S: .3}, art: {A: .8, R: .2}
}

/** The interest profile a student's SUBJECT confidence implies, which is a
 *  different thing from the interests they reported. Where the two disagree is
 *  the most useful thing this whole report can surface. */
export function subjectImpliedInterests(perf) {
  const sums = {}, weights = {}
  for (const subject of Object.keys(perf || {})) {
    const affinity = SUBJ_AFFINITY[subject]
    if (!affinity) continue
    for (const scale of Object.keys(affinity)) {
      const contribution = affinity[scale] * perf[subject].weight
      sums[scale] = (sums[scale] || 0) + perf[subject].score * contribution
      weights[scale] = (weights[scale] || 0) + contribution
    }
  }
  const out = {}
  for (const scale of Object.keys(weights)) if (weights[scale] > 0) out[scale] = sums[scale] / weights[scale]
  return out
}

/** Turn {math: 4, physics: 2, …} on a 1..5 confidence scale into the shape
 *  recSubjectFit expects. Returns null for an empty set -- silence is not a
 *  low mark. */
export function subjectPerformance(bySubject, scale) {
  const kind = scale || 'confidence'
  const range = SUBJECT_SCALES.scales[kind]
  const weight = SUBJECT_SCALES.weights[kind]
  const out = {}
  let n = 0
  for (const key of Object.keys(bySubject || {})) {
    let value = bySubject[key]
    if (value === null || value === undefined || isNaN(value)) continue
    value = Math.min(range.max, Math.max(range.min, value))
    out[key] = { score: (value - range.min) / (range.max - range.min), weight }
    n++
  }
  return n ? out : null
}

export const NAMES = {
 "careers": {
  "accountant": "Accountant",
  "actor": "Actor",
  "agronomist": "Agronomist",
  "ai_engineer": "AI Engineer",
  "animator": "Animator",
  "architect": "Architect",
  "artist": "Artist",
  "athlete": "Professional Athlete",
  "auditor": "Auditor",
  "banker": "Banking Specialist",
  "biologist": "Biologist",
  "business_analyst": "Business Analyst",
  "chef": "Chef",
  "chemist": "Chemist",
  "civil_engineer": "Civil Engineer",
  "coach": "Sports Coach",
  "construction_manager": "Construction Manager",
  "copywriter": "Copywriter",
  "cybersecurity": "Cybersecurity Engineer",
  "data_scientist": "Data Scientist",
  "dentist": "Dentist",
  "diplomat": "Diplomat",
  "doctor": "Doctor",
  "ecologist": "Ecologist",
  "editor": "Editor",
  "electrical_engineer": "Electrical Engineer",
  "electrician": "Electrician",
  "entrepreneur": "Entrepreneur",
  "environmental_scientist": "Environmental Scientist",
  "event_manager": "Event Manager",
  "farm_manager": "Farm Manager",
  "fashion_designer": "Fashion Designer",
  "financial_analyst": "Financial Analyst",
  "fitness_trainer": "Fitness Trainer",
  "food_technologist": "Food Technologist",
  "frontend_developer": "Frontend Developer",
  "geneticist": "Geneticist",
  "graphic_designer": "Graphic Designer",
  "hotel_manager": "Hotel Manager",
  "hr_specialist": "HR Specialist",
  "industrial_designer": "Industrial Designer",
  "industrial_engineer": "Industrial Engineer",
  "interior_designer": "Interior Designer",
  "investment_analyst": "Investment Analyst",
  "journalist": "Journalist",
  "judge": "Judge",
  "lab_technician": "Laboratory Technician",
  "landscape_designer": "Landscape Designer",
  "lawyer": "Lawyer",
  "legal_advisor": "Legal Advisor",
  "logistician": "Logistics Specialist",
  "marketing_manager": "Marketing Manager",
  "mechanical_engineer": "Mechanical Engineer",
  "methodologist": "Education Methodologist",
  "mobile_developer": "Mobile Developer",
  "musician": "Musician",
  "notary": "Notary",
  "nurse": "Nurse",
  "operations_manager": "Operations Manager",
  "paramedic": "Paramedic",
  "pe_teacher": "PE Teacher",
  "pharmacist": "Pharmacist",
  "photographer": "Photographer",
  "physicist": "Physicist",
  "physiotherapist": "Physiotherapist",
  "primary_teacher": "Primary School Teacher",
  "product_manager": "Product Manager",
  "prosecutor": "Prosecutor",
  "psychologist": "Psychologist",
  "researcher": "Researcher",
  "restaurant_manager": "Restaurant Manager",
  "robotics_engineer": "Robotics Engineer",
  "sales_manager": "Sales Manager",
  "school_counselor": "School Counsellor",
  "school_principal": "School Principal",
  "smm_specialist": "Social Media Specialist",
  "social_worker": "Social Worker",
  "software_engineer": "Software Engineer",
  "speech_therapist": "Speech Therapist",
  "sports_manager": "Sports Manager",
  "supply_chain_manager": "Supply Chain Manager",
  "surgeon": "Surgeon",
  "surveyor": "Surveyor",
  "systems_analyst": "Systems Analyst",
  "tax_specialist": "Tax Specialist",
  "teacher": "Subject Teacher",
  "technician": "Technician",
  "therapist": "Therapist",
  "tour_guide": "Tour Guide",
  "travel_agent": "Travel Agent",
  "tutor": "Tutor",
  "tv_producer": "TV Producer",
  "university_lecturer": "University Lecturer",
  "urban_planner": "Urban Planner",
  "veterinarian": "Veterinarian",
  "warehouse_manager": "Warehouse Manager"
 },
 "families": {
  "agriculture": "Agriculture, Food & Environment",
  "architecture": "Architecture & Design",
  "arts": "Arts & Entertainment",
  "business": "Business & Entrepreneurship",
  "cs": "Computer Science & AI",
  "education": "Education",
  "engineering": "Engineering & Robotics",
  "finance": "Finance & Economics",
  "hospitality": "Hospitality & Tourism",
  "law": "Law, Government & Diplomacy",
  "logistics": "Logistics, Construction & Technical",
  "media": "Media & Communication",
  "medicine": "Medicine & Healthcare",
  "psychology": "Psychology & Human Development",
  "science": "Science & Research",
  "sport": "Sports & Performance"
 },
 "majors": {
  "major_accounting": "Accounting",
  "major_agronomy": "Agronomy",
  "major_architecture": "Architecture",
  "major_banking": "Banking",
  "major_biology": "Biology",
  "major_biotechnology": "Biotechnology",
  "major_business_admin": "Business Administration",
  "major_chemistry": "Chemistry",
  "major_civil_eng": "Civil Engineering",
  "major_construction_management": "Construction Management",
  "major_cs": "Computer Engineering",
  "major_culinary": "Culinary Arts",
  "major_data_science": "Data Science",
  "major_dentistry": "Dentistry",
  "major_ecology": "Ecology",
  "major_economics": "Economics",
  "major_electrical_eng": "Electrical Power Engineering",
  "major_finance": "Finance",
  "major_fine_arts": "Fine Arts",
  "major_food_technology": "Food Technology",
  "major_graphic_design": "Graphic Design",
  "major_hotel_management": "Hotel Management",
  "major_info_security": "Information Security",
  "major_interior_design": "Interior Design",
  "major_international_relations": "International Relations",
  "major_journalism": "Journalism",
  "major_law": "Law",
  "major_logistics": "Logistics",
  "major_management": "Management",
  "major_marketing": "Marketing",
  "major_mechanical_eng": "Mechanical Engineering",
  "major_mechatronics": "Mechatronics and Robotics",
  "major_media_communications": "Media and Communications",
  "major_medicine": "Medicine",
  "major_music": "Music",
  "major_nursing": "Nursing",
  "major_pedagogy": "Pedagogy",
  "major_pharmacy": "Pharmacy",
  "major_philology": "Philology",
  "major_physical_education": "Physical Education",
  "major_physics": "Physics",
  "major_physiotherapy": "Physiotherapy",
  "major_political_science": "Political Science",
  "major_pr": "Public Relations",
  "major_primary_education": "Primary Education",
  "major_psychology": "Psychology",
  "major_social_work": "Social Work",
  "major_software_eng": "Software Engineering",
  "major_special_education": "Special Education",
  "major_sports_science": "Sports Science",
  "major_theatre": "Theatre Arts",
  "major_tourism": "Tourism",
  "major_transport": "Transport Systems",
  "major_urban_planning": "Urban Planning",
  "major_veterinary": "Veterinary Medicine"
 },
 "subjects": {
  "art": "Art and design",
  "biology": "Biology",
  "chemistry": "Chemistry",
  "cs": "Computer Science",
  "economics": "Economics",
  "english": "English",
  "geography": "Geography",
  "history": "History",
  "literature": "Native language and literature",
  "math": "Mathematics",
  "physics": "Physics"
 }
}

// TestMind — transparent career and major recommendation.
//
// No model, no AI, no learned weights. Every number here can be traced by hand,
// which matters more than sophistication: a school will be asked "why did it say
// that about my child", and the answer has to be a sentence, not a matrix.
//
// FOUR SIGNALS, AND WHY EACH IS SHAPED THE WAY IT IS
// --------------------------------------------------
// interests (RIASEC)  what the student currently enjoys      -- dominant
// values              what they want FROM a job              -- separates ties
// subjects            what they can already demonstrate      -- evidence
// personality         how they tend to work                  -- context only
//
// IPSATIVE, NOT ABSOLUTE. Interests and values are read RELATIVE to the
// student's own range, not on the raw 1..5. A teenager who likes everything and
// one who likes nothing would otherwise be ranked by how enthusiastic they are
// rather than by what they actually prefer. Subject marks are the exception:
// a 5 is a 5, so those stay absolute.
//
// PERSONALITY CANNOT BLOCK A CAREER. This is a product rule, and it is enforced
// arithmetically rather than by good intentions: the personality term
// contributes between HALF its weight and ALL of it, never zero. A quiet student
// therefore loses at most a few percent against entrepreneur -- they can never
// be ruled out of it. See personalityTerm().
//
// MISSING DATA IS NOT ZERO. A signal that was not collected is dropped and the
// remaining weights are renormalised, so a student who skipped the subject
// section is ranked on interests and values alone rather than being told they
// are bad at everything.
//
// NO PERCENTAGES ARE SHOWN. Scores exist to ORDER things. A "87% suitable"
// number would be false precision built on a ten-item value scale and a handful
// of self-entered marks, so the UI gets bands instead: strong / worth exploring
// / alternative.

export const REC_WEIGHTS = {
  // Interests lead for careers: what a person enjoys doing predicts occupational
  // choice better than what they are currently graded on at fifteen.
  career: { riasec: 0.50, values: 0.22, subjects: 0.20, personality: 0.08 },
  // Majors invert the middle two. Admission and survival in a degree depend on
  // demonstrated academic performance far more than a career does, and a major
  // is a narrower, more academic commitment than "work in this area".
  major:  { riasec: 0.36, values: 0.12, subjects: 0.44, personality: 0.08 }
};

// A part is only counted when it has data. These are the minimums below which a
// signal is treated as absent rather than weak.
export const REC_MIN_SUBJECT_WEIGHT = 0.15;   // of an entry's subject weights, must be covered

export function recKeys(o){ var k = [], x; for (x in o) if (o.hasOwnProperty(x)) k.push(x); return k; }

/** Rescale a profile to 0..1 across the student's OWN range.
 *  Returns null when the student has no spread at all (liked everything the
 *  same), because a flat profile expresses no preference and must not be
 *  allowed to masquerade as one. */
export function recRelative(profile){
  var keys = recKeys(profile || {});
  if (keys.length < 2) return null;
  var lo = Infinity, hi = -Infinity, i, v;
  for (i = 0; i < keys.length; i++){
    v = profile[keys[i]];
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (hi - lo < 1e-9) return null;
  var out = {};
  for (i = 0; i < keys.length; i++) out[keys[i]] = (profile[keys[i]] - lo) / (hi - lo);
  return out;
}

/** Weighted overlap between a student's relative profile and an entry's profile.
 *  The entry's weights sum to 1, so the result is already 0..1. */
export function recOverlap(rel, entryProfile){
  if (!rel) return null;
  var keys = recKeys(entryProfile), sum = 0, w = 0, i, k;
  for (i = 0; i < keys.length; i++){
    k = keys[i];
    if (!(k in rel)) continue;
    sum += entryProfile[k] * rel[k];
    w += entryProfile[k];
  }
  return w > 0 ? sum / w : null;
}

/** How well the student's marks cover what this entry leans on.
 *  Absolute, not relative: a 5 in mathematics means the same for everyone.
 *  Null when the student entered nothing relevant -- silence is not a low mark. */
export function recSubjectFit(perf, entrySubjects){
  if (!perf) return null;
  var keys = recKeys(entrySubjects), sum = 0, w = 0, covered = 0, i, k, rec;
  for (i = 0; i < keys.length; i++){
    k = keys[i];
    rec = perf[k];
    if (!rec) continue;
    // A self-reported answer counts less than a real mark; `weight` carries that.
    var ew = entrySubjects[k] * (rec.weight === undefined ? 1 : rec.weight);
    sum += ew * rec.score;
    w += ew;
    covered += entrySubjects[k];
  }
  if (w <= 0 || covered < REC_MIN_SUBJECT_WEIGHT) return null;
  // Shrink toward neutral in proportion to how much of the entry we could
  // actually see. Without this, an entry needing three subjects the student
  // supplied two of scores a perfect 1.00 and ties with one whose every
  // requirement was covered -- a student with 5s in maths, CS and physics tied
  // finance (which ignores physics) with computer science. Partial evidence is
  // now worth proportionally less, and symmetrically: a poor mark on thin
  // coverage is also less damning than a poor mark on full coverage.
  return 0.5 + (sum / w - 0.5) * covered;
}

/** Personality's contribution, deliberately bounded away from zero.
 *
 *  Big Five is 1..5 per trait. Two traits are used, and only where there is a
 *  defensible link: Extraversion against how much an entry is about persuading
 *  and leading (its Enterprising weight), Conscientiousness against how much it
 *  is about order and procedure (its Conventional weight).
 *
 *  The return is 0.5..1.0, never 0..1. That is the whole mechanism behind
 *  "personality must not block a career": at full weight 0.08 the most
 *  personality can ever move an entry is 4 percentage points, and it can only
 *  ever add. A quiet student stays eligible for entrepreneur. */
export function recPersonalityTerm(big5, entryRiasec){
  if (!big5 || big5.E === undefined) return null;
  var e = (big5.E - 1) / 4;                       // 0..1
  var c = (big5.C - 1) / 4;
  var wE = entryRiasec.E || 0, wC = entryRiasec.C || 0;
  var w = wE + wC;
  if (w <= 0) return 0.75;                        // no defensible link: neutral
  var fit = (wE * e + wC * c) / w;                // 0..1
  return 0.5 + 0.5 * fit;                         // 0.5..1
}

/** Score one entry. Returns {score, parts, used} or null when nothing applied. */
export function recScoreEntry(entry, signals, weights){
  var parts = {}, total = 0, wsum = 0;

  var riasec = recOverlap(signals.riasecRel, entry.riasec);
  if (riasec !== null){ parts.riasec = riasec; total += weights.riasec * riasec; wsum += weights.riasec; }

  var values = recOverlap(signals.valuesRel, entry.values);
  if (values !== null){ parts.values = values; total += weights.values * values; wsum += weights.values; }

  var subj = recSubjectFit(signals.subjects, entry.subjects);
  if (subj !== null){ parts.subjects = subj; total += weights.subjects * subj; wsum += weights.subjects; }

  var pers = recPersonalityTerm(signals.big5, entry.riasec);
  if (pers !== null){ parts.personality = pers; total += weights.personality * pers; wsum += weights.personality; }

  if (wsum <= 0) return null;                     // no signal at all
  return { score: total / wsum, parts: parts, used: recKeys(parts) };
}

/** Turn a student's raw scores into the shapes the scorer wants, once. */
export function recSignals(riasec, values, subjects, big5){
  return {
    riasecRel: recRelative(riasec),
    valuesRel: recRelative(values),
    subjects: (subjects && recKeys(subjects).length) ? subjects : null,
    big5: big5 || null
  };
}

// Banding is by GAP FROM THE BEST, not by position in the whole range.
// Measured over 96 careers, the five that get displayed sit within 0.00-0.20 of
// the top score while the full range is ~0.90 -- so a range-based cut put every
// displayed row in the top quartile and every dot came out green, which told the
// reader nothing. What a student can act on is "how much weaker is this than the
// strongest one", and these thresholds come from that measured spread.
export const REC_BAND_STRONG = 0.04;
export const REC_BAND_EXPLORE = 0.10;

/** Band a ranked row. `worst` is still needed to detect the degenerate case
 *  where nothing separates anything, in which case nothing is claimed. */
export function recBand(score, best, worst){
  if (best - worst < 1e-6) return 'explore';      // everything tied: claim nothing
  var gap = best - score;
  if (gap <= REC_BAND_STRONG) return 'strong';
  if (gap <= REC_BAND_EXPLORE) return 'explore';
  return 'alternative';
}

/** Rank every entry in a table. `kind` is 'career' or 'major'. */
export function recRank(table, signals, kind, limit){
  var weights = REC_WEIGHTS[kind], keys = recKeys(table), rows = [], i, r;
  for (i = 0; i < keys.length; i++){
    r = recScoreEntry(table[keys[i]], signals, weights);
    if (r) rows.push({ key: keys[i], score: r.score, parts: r.parts,
                       used: r.used, family: table[keys[i]].family,
                       education: table[keys[i]].education });
  }
  if (!rows.length) return [];
  rows.sort(function(a, b){ return (b.score - a.score) || (a.key < b.key ? -1 : 1); });
  var best = rows[0].score, worst = rows[rows.length - 1].score;
  for (i = 0; i < rows.length; i++) rows[i].band = recBand(rows[i].score, best, worst);
  return limit ? rows.slice(0, limit) : rows;
}

/** Rank the FAMILIES, which is the level a fifteen-year-old can act on. */
export function recRankFamilies(families, signals, limit){
  var keys = recKeys(families), rows = [], i, r;
  for (i = 0; i < keys.length; i++){
    r = recScoreEntry(families[keys[i]], signals, REC_WEIGHTS.career);
    if (r) rows.push({ key: keys[i], score: r.score, parts: r.parts, used: r.used });
  }
  rows.sort(function(a, b){ return (b.score - a.score) || (a.key < b.key ? -1 : 1); });
  if (rows.length){
    var best = rows[0].score, worst = rows[rows.length - 1].score;
    for (i = 0; i < rows.length; i++) rows[i].band = recBand(rows[i].score, best, worst);
  }
  return limit ? rows.slice(0, limit) : rows;
}

/** Which signals actually drove this row, strongest first.
 *  Contribution, not raw part value: a part scoring 0.9 at weight 0.08 mattered
 *  less than one scoring 0.6 at weight 0.5, and the explanation must say so. */
export function recDrivers(row, kind){
  var w = REC_WEIGHTS[kind], out = [], k;
  for (k in row.parts) if (row.parts.hasOwnProperty(k))
    out.push({ part: k, contribution: row.parts[k] * w[k], value: row.parts[k] });
  out.sort(function(a, b){ return b.contribution - a.contribution; });
  return out;
}

/** Signals that disagree, which is the most useful thing a report can surface.
 *  Returns [] when they agree -- a conflict claimed where none exists is worse
 *  than none reported. */
export function recConflicts(signals, subjectImplied){
  var out = [];
  var a = signals.riasecRel, b = recRelative(subjectImplied || {});
  if (!a || !b) return out;
  var k, gap;
  for (k in a) if (a.hasOwnProperty(k) && b.hasOwnProperty(k)){
    gap = a[k] - b[k];
    if (gap >= 0.5) out.push({ scale: k, side: 'interest', gap: gap });
    else if (gap <= -0.5) out.push({ scale: k, side: 'marks', gap: -gap });
  }
  out.sort(function(x, y){ return y.gap - x.gap; });
  return out;
}

if (typeof module !== 'undefined' && module.exports){
  module.exports = {
    REC_WEIGHTS: REC_WEIGHTS, recRelative: recRelative, recOverlap: recOverlap,
    recSubjectFit: recSubjectFit, recPersonalityTerm: recPersonalityTerm,
    recScoreEntry: recScoreEntry, recSignals: recSignals, recBand: recBand,
    REC_BAND_STRONG: REC_BAND_STRONG, REC_BAND_EXPLORE: REC_BAND_EXPLORE,
    recRank: recRank, recRankFamilies: recRankFamilies,
    recDrivers: recDrivers, recConflicts: recConflicts
  };
}
