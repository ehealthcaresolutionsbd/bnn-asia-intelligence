"""Reference data. Contains only factual identifiers (names, ISO codes) – no scores."""

REGIONS = [
    ("Asia", "asia", None, "142"),
    ("South Asia", "south-asia", "asia", "034"),
    ("Southeast Asia", "southeast-asia", "asia", "035"),
    ("East Asia", "east-asia", "asia", "030"),
    ("Central Asia", "central-asia", "asia", "143"),
    ("West Asia / Middle East", "west-asia", "asia", "145"),
]

# name, iso2, iso3, region slug, capital, flag, aliases
COUNTRIES = [
    ("Afghanistan", "AF", "AFG", "south-asia", "Kabul", "🇦🇫", ["Afghan"]),
    ("Bangladesh", "BD", "BGD", "south-asia", "Dhaka", "🇧🇩", ["Bangladeshi", "Dhaka"]),
    ("Bhutan", "BT", "BTN", "south-asia", "Thimphu", "🇧🇹", ["Bhutanese"]),
    ("India", "IN", "IND", "south-asia", "New Delhi", "🇮🇳", ["Indian", "New Delhi", "Kashmir"]),
    ("Maldives", "MV", "MDV", "south-asia", "Malé", "🇲🇻", ["Maldivian"]),
    ("Nepal", "NP", "NPL", "south-asia", "Kathmandu", "🇳🇵", ["Nepali", "Nepalese", "Kathmandu"]),
    ("Pakistan", "PK", "PAK", "south-asia", "Islamabad", "🇵🇰", ["Pakistani", "Islamabad", "Karachi", "Lahore"]),
    ("Sri Lanka", "LK", "LKA", "south-asia", "Sri Jayawardenepura Kotte", "🇱🇰", ["Sri Lankan", "Colombo"]),
    ("Brunei", "BN", "BRN", "southeast-asia", "Bandar Seri Begawan", "🇧🇳", ["Brunei Darussalam"]),
    ("Cambodia", "KH", "KHM", "southeast-asia", "Phnom Penh", "🇰🇭", ["Cambodian", "Phnom Penh"]),
    ("Indonesia", "ID", "IDN", "southeast-asia", "Jakarta", "🇮🇩", ["Indonesian", "Jakarta", "Papua"]),
    ("Laos", "LA", "LAO", "southeast-asia", "Vientiane", "🇱🇦", ["Lao PDR", "Lao People's Democratic Republic", "Laotian"]),
    ("Malaysia", "MY", "MYS", "southeast-asia", "Kuala Lumpur", "🇲🇾", ["Malaysian", "Kuala Lumpur"]),
    ("Myanmar", "MM", "MMR", "southeast-asia", "Naypyidaw", "🇲🇲", ["Burma", "Burmese", "Yangon", "Rakhine"]),
    ("Philippines", "PH", "PHL", "southeast-asia", "Manila", "🇵🇭", ["Filipino", "Philippine", "Manila", "Mindanao"]),
    ("Singapore", "SG", "SGP", "southeast-asia", "Singapore", "🇸🇬", ["Singaporean"]),
    ("Thailand", "TH", "THA", "southeast-asia", "Bangkok", "🇹🇭", ["Thai", "Bangkok"]),
    ("Timor-Leste", "TL", "TLS", "southeast-asia", "Dili", "🇹🇱", ["East Timor", "Timorese"]),
    ("Vietnam", "VN", "VNM", "southeast-asia", "Hanoi", "🇻🇳", ["Viet Nam", "Vietnamese", "Hanoi"]),
    ("China", "CN", "CHN", "east-asia", "Beijing", "🇨🇳", ["Chinese", "Beijing", "Xinjiang", "Tibet", "Hong Kong"]),
    ("Japan", "JP", "JPN", "east-asia", "Tokyo", "🇯🇵", ["Japanese", "Tokyo"]),
    ("Mongolia", "MN", "MNG", "east-asia", "Ulaanbaatar", "🇲🇳", ["Mongolian"]),
    ("North Korea", "KP", "PRK", "east-asia", "Pyongyang", "🇰🇵", ["DPRK", "Korea, Dem. People's Rep.", "Pyongyang"]),
    ("South Korea", "KR", "KOR", "east-asia", "Seoul", "🇰🇷", ["Republic of Korea", "Korea, Rep.", "Seoul", "Korean"]),
    ("Taiwan", "TW", "TWN", "east-asia", "Taipei", "🇹🇼", ["Taiwanese", "Taipei"]),
    ("Kazakhstan", "KZ", "KAZ", "central-asia", "Astana", "🇰🇿", ["Kazakh"]),
    ("Kyrgyzstan", "KG", "KGZ", "central-asia", "Bishkek", "🇰🇬", ["Kyrgyz Republic", "Kyrgyz"]),
    ("Tajikistan", "TJ", "TJK", "central-asia", "Dushanbe", "🇹🇯", ["Tajik"]),
    ("Turkmenistan", "TM", "TKM", "central-asia", "Ashgabat", "🇹🇲", ["Turkmen"]),
    ("Uzbekistan", "UZ", "UZB", "central-asia", "Tashkent", "🇺🇿", ["Uzbek"]),
    ("Bahrain", "BH", "BHR", "west-asia", "Manama", "🇧🇭", ["Bahraini"]),
    ("Iran", "IR", "IRN", "west-asia", "Tehran", "🇮🇷", ["Iranian", "Islamic Republic of Iran", "Iran, Islamic Rep.", "Tehran"]),
    ("Iraq", "IQ", "IRQ", "west-asia", "Baghdad", "🇮🇶", ["Iraqi", "Baghdad", "Kurdistan"]),
    ("Israel", "IL", "ISR", "west-asia", "Jerusalem", "🇮🇱", ["Israeli"]),
    ("Jordan", "JO", "JOR", "west-asia", "Amman", "🇯🇴", ["Jordanian"]),
    ("Kuwait", "KW", "KWT", "west-asia", "Kuwait City", "🇰🇼", ["Kuwaiti"]),
    ("Lebanon", "LB", "LBN", "west-asia", "Beirut", "🇱🇧", ["Lebanese", "Beirut"]),
    ("Oman", "OM", "OMN", "west-asia", "Muscat", "🇴🇲", ["Omani"]),
    ("Palestine", "PS", "PSE", "west-asia", "Ramallah", "🇵🇸", ["Palestinian", "Gaza", "West Bank", "West Bank and Gaza", "State of Palestine"]),
    ("Qatar", "QA", "QAT", "west-asia", "Doha", "🇶🇦", ["Qatari", "Doha"]),
    ("Saudi Arabia", "SA", "SAU", "west-asia", "Riyadh", "🇸🇦", ["Saudi", "Riyadh"]),
    ("Syria", "SY", "SYR", "west-asia", "Damascus", "🇸🇾", ["Syrian", "Syrian Arab Republic", "Damascus"]),
    ("Turkey", "TR", "TUR", "west-asia", "Ankara", "🇹🇷", ["Türkiye", "Turkiye", "Turkish", "Ankara", "Istanbul"]),
    ("United Arab Emirates", "AE", "ARE", "west-asia", "Abu Dhabi", "🇦🇪", ["UAE", "Emirati", "Dubai", "Abu Dhabi"]),
    ("Yemen", "YE", "YEM", "west-asia", "Sanaa", "🇾🇪", ["Yemeni", "Yemen, Rep.", "Sanaa", "Aden"]),
    ("Armenia", "AM", "ARM", "west-asia", "Yerevan", "🇦🇲", ["Armenian"]),
    ("Azerbaijan", "AZ", "AZE", "west-asia", "Baku", "🇦🇿", ["Azerbaijani", "Baku"]),
    ("Georgia", "GE", "GEO", "west-asia", "Tbilisi", "🇬🇪", ["Georgian", "Tbilisi"]),
]

CATEGORIES = [
    # slug, name, order, enabled, description
    ("good-governance", "Good Governance", 1, True, "Government effectiveness, regulatory quality, control of corruption and transparency."),
    ("human-rights", "Human Rights", 2, True, "Documented violations: disappearances, arbitrary detention, torture, custodial deaths, attacks on defenders and minorities."),
    ("press-freedom", "Press Freedom", 3, True, "Safety of journalists and the legal, political and economic environment for independent media."),
    ("freedom-democracy", "Freedom & Democracy", 4, False, "Political rights, civil liberties and voice & accountability. Disabled at launch."),
    ("rule-of-law", "Rule of Law", 5, True, "Confidence in and abidance by the rules of society, judicial independence and access to justice."),
    ("economic-social", "Economic & Social Wellbeing", 6, True, "Income, growth, prices, employment and human development."),
]

INCIDENT_TYPES = [
    ("Enforced Disappearance", "human-rights"), ("Extrajudicial Killing Allegation", "human-rights"),
    ("Arbitrary Arrest", "human-rights"), ("Political Detention", "human-rights"), ("Torture", "human-rights"),
    ("Custodial Death", "human-rights"), ("Protest Violence", "human-rights"), ("Reported Injuries", "human-rights"),
    ("Reported Deaths", "human-rights"), ("Journalist Arrest", "press-freedom"), ("Journalist Killing", "press-freedom"),
    ("Journalist Disappearance", "press-freedom"), ("Human Rights Defender Attack", "human-rights"),
    ("Minority Rights Violation", "human-rights"), ("Freedom of Expression Violation", "press-freedom"),
]

# Keyword hints used ONLY to suggest a type for researcher triage (never to create incidents).
INCIDENT_KEYWORDS = {
    "enforced-disappearance": ["enforced disappearance", "disappeared", "abducted", "missing activist"],
    "extrajudicial-killing-allegation": ["extrajudicial", "crossfire", "encounter killing", "killed by police", "killed by security forces"],
    "arbitrary-arrest": ["arbitrary arrest", "arbitrarily detained", "detained without charge", "arrested"],
    "political-detention": ["political prisoner", "opposition leader detained", "detained activist"],
    "torture": ["torture", "tortured", "ill-treatment"],
    "custodial-death": ["died in custody", "custodial death", "death in custody"],
    "protest-violence": ["protesters", "crackdown on protest", "tear gas", "live ammunition"],
    "journalist-arrest": ["journalist arrested", "reporter arrested", "journalist detained", "editor arrested"],
    "journalist-killing": ["journalist killed", "journalist shot", "reporter killed", "journalist murdered"],
    "journalist-disappearance": ["journalist missing", "journalist abducted", "journalist disappeared"],
    "human-rights-defender-attack": ["human rights defender", "rights activist attacked", "lawyer attacked"],
    "minority-rights-violation": ["minority", "rohingya", "uyghur", "ahmadi", "dalit", "hindu minority", "christian minority"],
    "freedom-of-expression-violation": ["censorship", "blocked website", "internet shutdown", "blasphemy", "defamation case", "cyber security act"],
}
