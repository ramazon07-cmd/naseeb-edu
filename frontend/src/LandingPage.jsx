import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Building2,
  ChevronRight,
  CircleDollarSign,
  ClipboardCheck,
  Compass,
  FileText,
  Globe2,
  GraduationCap,
  HeartHandshake,
  Mail,
  MessageSquareText,
  Moon,
  PenLine,
  Presentation,
  ShieldCheck,
  Sun,
  UserRoundCheck,
} from "lucide-react";

import { LANGUAGE_OPTIONS, formatNumberLocale, t, tx } from "./i18n";
import {
  CounselorDashboardPreview,
  StudentDashboardPreview,
} from "./LandingDashboardPreviews";
import HeroParticleNetwork from "./HeroParticleNetwork";
import "./landing.css";

/* ---------------------------------------------------------------------------
   TEAM — the real founding team. Empty the array and the whole band, plus its
   footer link, disappears rather than showing an empty roster.

   `name` and `email` are a real person's identity: never wrap them in t(), and
   never add, change or reword an entry without asking that person. `role` and
   `note` are copy and are translated.

   Portraits: drop a SQUARE image at frontend/public/landing/team/<file> and set
   `photo` to the file name. The expected files are listed in that directory's
   README. Without one the entry renders its initials monogram — a designed
   state, not a gap — so a missing photo never breaks the row.
--------------------------------------------------------------------------- */
const TEAM = [
  {
    id: "team-humoyun",
    name: "Humoyun Nasipkulov",
    initials: "HN",
    photo: "humoyun.jpg",
    role: "Founder",
    note: "ex-Walt Disney",
    email: "khumoyun@naseebedu.com",
  },
  {
    id: "team-firdavs",
    name: "Firdavsbek Juraev",
    initials: "FJ",
    photo: "firdavs.jpg",
    role: "COO",
    note: "Apple Academy ’24",
    email: "firdavs@naseebedu.com",
  },
  {
    id: "team-sevinchkhon",
    name: "Sevinchkhon Amanova",
    initials: "SA",
    photo: "sevinchkhon.jpg",
    role: "CEO",
    note: "EdManagement 3+ y.",
    email: "sevinchkhon@naseebedu.com",
  },
  {
    id: "team-asadbek",
    name: "Asadbek Ismoilov",
    initials: "AI",
    photo: "asadbek.jpg",
    role: "CPO",
    note: "Admission Expert",
    email: "asadbek@naseebedu.com",
  },
  {
    id: "team-shakhriyor",
    name: "Shakhriyor Pulatov",
    initials: "SP",
    photo: "shakhriyor.jpg",
    role: "CTO",
    note: "6 y. in Data Integrity Services.",
    email: "shakhriyor@naseebedu.com",
  },
];

/* ---------------------------------------------------------------------------
   STUDENT REVIEWS — reference content supplied for this landing page. Names,
   outcomes, portraits and quotations stay together as a single record.
   Emptying the array removes the section and its navigation entries.
--------------------------------------------------------------------------- */
const STUDENT_REVIEWS = [
  {
    id: "review-nurbek-alisherov",
    name: "Alisherov Nurbek",
    initials: "AK",
    photo: "nurbek.jpg",
    university: "The Education University of Hong Kong (EdUHK)",
    quote: `Before joining Naseeb Edu, I was confused about choosing between Computer Science and Education. My mentors helped me discover Educational Technology — a field I did not even know existed, but which perfectly combines the two subjects I love most.

Throughout the process, I learned much more than just how to write essays. Naseeb Edu helped me grow personally, present my achievements and passions effectively, and strengthen my portfolio through international and national opportunities.

With their guidance, I received a full-ride scholarship to The Education University of Hong Kong. It was an unforgettable journey.`,
  },

  {
    id: "review-polyu-student",
    name: "Rajabov Dilshodbek",
    initials: "RD",
    photo: "dilshod.jpg",
    university: "The Hong Kong Polytechnic University (PolyU)",
    scholarship: "",
    quote: `Before joining Naseeb Edu, I already knew I wanted to study Tourism and Hospitality abroad, but I had no idea where to apply or how to begin.

Naseeb Edu helped me research countries and universities and introduced me to Hong Kong and PolyU. I realized that Hong Kong was an ideal place to study modern tourism because it is one of the world’s most dynamic international destinations.

What excited me most about PolyU was its practical approach to hospitality education, including the opportunity to gain real experience at Hotel ICON, its own luxury teaching hotel. Naseeb Edu helped me turn a broad interest into a clear university and career direction.`,
  },

  {
    id: "review-yale-student",
    name: "Diyorbek Bakhtiyorov",
    initials: "DB",
    photo: "diyorbek.jpg",
    university: "The Hong Kong University of Science and Technology  (HKUST)",
    quote: `My journey toward HKUST was not easy. There were moments when I felt overwhelmed, but whenever things became difficult, my mentors were there to guide and support me.

My story truly began in June 2026, when Firdavs Jurayev introduced us to the idea of building a strong student portfolio during a school assembly. Before that, I did not fully understand how important my time, activities, and experiences could be for my future.

At first, I thought I was simply joining another program. Over time, I realized I had become part of a community where everyone genuinely wanted to see me succeed. That support kept me moving forward throughout the application process.`,
  },

  {
    id: "review-law-student",
    name: "Amirali Isayev",
    initials: "AI",
    photo: "amirali.jpg",
    university: "Hong Kong University  (HKU)",
    scholarship: "",
    quote: `Working with the Naseeb Edu team has been insightful in many ways. Since joining the community, I have met many new people, made great friends, and had the opportunity to reflect more deeply on my interest in Law.

The team helped me understand how the university application process works and guided me as I continued working toward my goal of studying abroad.

I have dreamed of studying at an international university from a young age, and I am grateful to Naseeb Edu for helping me move closer to that goal.`,
  },

  {
    id: "review-cuhk-student",
    name: "Saidakmal Jalilov",
    initials: "SJ",
    photo: "saidakmal.jpg",
    university: "Vin University",
    scholarship: "",
    quote: `Before joining Naseeb Edu, I had ambitions to study abroad, but I was not completely sure how to turn those ambitions into a strong university application.

Working with the Naseeb Edu team helped me understand my strengths, reflect on my interests, and approach the application process with much more clarity. My mentors guided me through university research, essays, and building a stronger overall profile.

The journey taught me that applying to a competitive university is not only about grades. It is also about understanding yourself and communicating your story effectively. I am grateful to Naseeb Edu for supporting me throughout this process.`,
  },

  {
    id: "review-cityuhk-student",
    name: "Muhammadrizo Mirkhonov",
    initials: "MM",
    photo: "muhammadrizo.jpg",
    university: "Yonsei University",
    scholarship: "",
    quote: `When I first started thinking seriously about studying abroad, the number of universities, majors, and application requirements felt overwhelming.

Naseeb Edu helped me make the process much more structured. Through discussions with my mentors, I was able to identify universities that matched my academic interests and long-term goals, while also improving the way I presented my experiences in my application.

What I appreciated most was the personal guidance throughout the journey. I never felt like I was working on my application alone, and that support gave me much more confidence in applying to universities such as Yonsei University.`,
  },
];

/* ---------------------------------------------------------------------------
   Universities our students were admitted to. Add an entry only for a real,
   confirmed placement — this strip is a factual claim about our own students,
   not a partner or customer list.

   University logos live at frontend/public/landing/universities/<file>;
   scholarship and program logos live at frontend/public/landing/programs/<file>
   (SVG preferred, or a transparent PNG at least 2x the rendered 44px height).
   Use the mark the university publishes on its own brand/identity page, and
   follow that page's usage terms.

   While the array is empty the connected-roles strip stands in its place, so
   the band is never blank and never claims a placement we cannot show.
--------------------------------------------------------------------------- */
const UNIVERSITY_PLACEMENTS = [
  { name: "The University of Hong Kong", file: "hku.svg" },
  { name: "The Chinese University of Hong Kong", file: "cuhk.png" },
  { name: "Hong Kong University of Science and Technology", file: "hkust.svg" },
  { name: "The Hong Kong Polytechnic University", file: "polyu.png" },
  { name: "City University of Hong Kong", file: "cityu.png" },
  { name: "The Education University of Hong Kong", file: "eduhk.png" },
  { name: "Lingnan University", file: "lingnan.png" },
  { name: "Hong Kong Metropolitan University", file: "hkmu.png" },
  { name: "Korea University", file: "korea.png" },
  { name: "Yonsei University", file: "yonsei.png" },
  { name: "KAIST", file: "kaist.svg" },
  { name: "Seoul National University", file: "snu.png" },
  { name: "Northwestern University", file: "northwestern.svg", tone: "light" },
  { name: "EPFL", file: "epfl.svg" },
  { name: "University of Toronto", file: "toronto.png" },
  { name: "University of Alberta", file: "alberta.png" },
  { name: "State University of New York (SUNY)", file: "suny.png" },
  { name: "Hamad Bin Khalifa University", file: "hbku.svg" },
  { name: "University of South Florida", file: "usf.png" },
  { name: "University of Leeds", file: "leeds.svg" },
  { name: "University at Buffalo", file: "buffalo.png", tone: "light" },
  { name: "University of Arizona", file: "arizona.svg" },
  { name: "Arizona State University", file: "asu.png", tone: "light" },
  { name: "Virginia Tech", file: "virginia-tech.svg" },
  { name: "Purdue University", file: "purdue.svg" },
  { name: "University of Debrecen", file: "debrecen.svg" },
  { name: "Eötvös Loránd University (ELTE)", file: "elte.svg" },
  { name: "The College of Wooster", file: "wooster.svg" },
  { name: "Gettysburg College", file: "gettysburg.png", tone: "light" },
  { name: "Middle East Technical University (METU)", file: "metu.svg" },
  { name: "Bilkent University", file: "bilkent.svg" },
  { name: "Tokyo International University", file: "tiu.png" },
  { name: "VinUniversity", file: "vinuni.png" },
  { name: "New York University (NYU)", file: "nyu.svg" },
  { name: "Duke University", file: "duke.svg" },
  {
    name: "Pennsylvania State University",
    file: "penn-state.svg",
    tone: "light",
  },
  { name: "University of Minnesota", file: "minnesota.svg" },
  { name: "University of Cincinnati", file: "cincinnati.svg" },
  { name: "Drexel University", file: "drexel.svg" },
  { name: "Lynn University", file: "lynn.png" },
  { name: "University of Liverpool", file: "liverpool.svg" },
  { name: "University of Nottingham", file: "nottingham.svg", tone: "light" },
  { name: "Mount Allison University", file: "mount-allison.svg" },
  { name: "Waseda University", file: "waseda.svg" },
  { name: "Harbin Institute of Technology", file: "hit.png", tone: "light" },
  { name: "Constructor University", file: "constructor.svg", tone: "light" },
  { name: "The University of Sydney", file: "sydney.svg" },
];

const GOVERNMENT_SCHOLARSHIPS = [
  {
    name: "El-yurt umidi (EYUF)",
    file: "eyuf.svg",
    label: "EL-YURT\nUMIDI",
    caption: "JAMG‘ARMASI",
    layout: "lockup",
  },
  { name: "Stipendium Hungaricum", file: "stipendium-hungaricum.png" },
  { name: "Türkiye Bursları", file: "turkiye-burslari.png" },
  {
    name: "National Scholarship Programme of Slovakia (NSP)",
    file: "nsp.jpg",
    layout: "tall",
  },
  // HKSAR funder emblem, not a separately verified scholarship logo.
  {
    name: "Belt & Road Scholarship (HKSAR Government Scholarship Fund)",
    file: "hksar.svg",
    label: "Belt & Road\nScholarship",
    caption: "HKSAR Government",
    layout: "lockup",
    tone: "original",
  },
];

const INTERNATIONAL_PROGRAMS = [
  {
    name: "Apple Developer Academy",
    file: "apple-academy.webp",
    layout: "square",
  },
  { name: "Future Leaders Exchange (FLEX)", file: "flex.png" },
  { name: "United World Colleges (UWC)", file: "uwc.svg" },
  { name: "Lumiere Research", file: "lumiere-wordmark.png", tone: "light" },
  { name: "LaunchX", file: "launchx.svg", label: "LaunchX", tone: "original" },
  { name: "Veritas AI", file: "veritas.webp", tone: "light", layout: "square" },
];

// Keep each category in its own row. Each track repeats only its own entries
// once to make the marquee seamless; accessible lists never repeat them.
const PLACEMENT_ROWS = [
  {
    id: "universities",
    title: "Our students were admitted to",
    directory: "universities",
    entries: UNIVERSITY_PLACEMENTS,
  },
  {
    id: "scholarships-programs",
    title: "Government scholarships & international programs",
    directory: "programs",
    entries: [...GOVERNMENT_SCHOLARSHIPS, ...INTERNATIONAL_PROGRAMS],
  },
].filter(({ entries }) => entries.length > 0);

/* ---------------------------------------------------------------------------
   Frequently asked questions. Answers are product claims, so every line here
   must stay true of what the platform actually does: readiness is preparation
   progress and never an admission probability, accounts are provisioned by a
   school, and matching is profile-driven rather than a ranking table.
   `answer` is an array so a question can carry a qualifying second paragraph
   without a second component. The final entry is the contact hand-off and
   renders the support address as a real mailto action rather than prose.
--------------------------------------------------------------------------- */
const FAQS = [
  {
    id: "faq-counselor",
    question: "Who is a school counselor?",
    answer: [
      "A school counselor helps students understand their strengths, interests and career options. They guide students in choosing suitable majors and universities, finding scholarships, and preparing strong applications.",
    ],
  },
  {
    id: "faq-what",
    question: "What is Naseeb Edu?",
    answer: [
      "Naseeb Edu is a university and career counseling platform for schools. It brings student discovery, university matching, application planning, progress tracking and counselor guidance together in one structured system.",
    ],
  },
  {
    id: "faq-counselors",
    question: "How does Naseeb Edu help school counselors?",
    answer: [
      "Naseeb Edu gives counselors a clear overview of every student\u2019s journey. They can create personalized roadmaps, assign tasks, track progress, manage deadlines, review application materials and identify students who need additional support.",
    ],
  },
  {
    id: "faq-students",
    question: "What can students do on Naseeb Edu?",
    answer: [
      "Students can explore their personality, interests and career options, discover matching universities, follow a personalized roadmap, manage tasks and deadlines, prepare application materials and message their counselor \u2014 all from one account.",
    ],
  },
  {
    id: "faq-discovery",
    question: "How does Naseeb Edu help students discover their path?",
    answer: [
      "Naseeb Edu helps students explore their personality, interests and possible career paths before choosing a major or university. These insights give students a clearer understanding of themselves and help counselors provide more personalized guidance.",
    ],
  },
  {
    id: "faq-match",
    question: "How does University Match work?",
    answer: [
      "University Match uses each student\u2019s profile \u2014 interests, career goals, academic performance, test scores, financial needs and preferences \u2014 to recommend suitable universities. Students explore and compare those options with guidance from their counselor.",
    ],
  },
  {
    id: "faq-progress",
    question: "Can schools and parents track student progress?",
    answer: [
      "Yes. Naseeb Edu shows each student\u2019s university readiness as a clear percentage based on completed tasks and application milestones. Schools monitor progress through their dashboard, and parents review it from the student\u2019s account.",
      "The readiness percentage reflects preparation progress, not the probability of admission.",
    ],
  },
  {
    id: "faq-join",
    question: "How can my school join Naseeb Edu?",
    answer: [
      "Contact our team to tell us about your school and counseling needs. We will introduce the platform, help set up your school workspace, and guide your counselors and students through onboarding.",
    ],
  },
  {
    id: "faq-contact",
    question: "Didn\u2019t find your question?",
    answer: ["Send it to our team and we will answer it directly."],
    contact: true,
  },
];

const SUPPORT_EMAIL = (
  import.meta.env.VITE_SUPPORT_EMAIL || "support@naseebedu.com"
).trim();
/* The registered place of business, printed as it is filed. A postal address
   is a proper noun, not copy: it stays in Uzbek in every language. */
const DEFAULT_CONTACT_LOCATION =
  "Toshkent shahri, Olmazor tumani, Miskin MFY, Shimoliy Olmazor-2 mavzesi, 13-uy, 17-xonadon";
const CONTACT_LOCATION = (
  import.meta.env.VITE_CONTACT_LOCATION || DEFAULT_CONTACT_LOCATION
).trim();
const CONTACT_PHONE = (
  import.meta.env.VITE_CONTACT_PHONE || "+998 99 100 54 10"
).trim();
const SCHOOL_CONTACT_URL = (
  import.meta.env.VITE_SCHOOL_CONTACT_URL || ""
).trim();
const DEFAULT_BOOK_MEETING_URL =
  "https://calendly.com/khumoyunnasipkulov/full-support-asia";
const BOOK_MEETING_URL = (
  import.meta.env.VITE_BOOK_MEETING_URL || DEFAULT_BOOK_MEETING_URL
).trim();
/* Network names are proper nouns and are printed, not translated. The footer
   sets them as words rather than icons, so no glyph is carried for them. */
const SOCIAL_LINKS = [
  {
    label: "Telegram",
    href: (
      import.meta.env.VITE_TELEGRAM_URL || "https://t.me/naseeb_edu"
    ).trim(),
  },
  {
    label: "Instagram",
    href: (
      import.meta.env.VITE_INSTAGRAM_URL ||
      "https://www.instagram.com/naseeb_edu/"
    ).trim(),
  },
  {
    label: "LinkedIn",
    href: (
      import.meta.env.VITE_LINKEDIN_URL ||
      "https://www.linkedin.com/company/naseeb-edu"
    ).trim(),
  },
  {
    label: "YouTube",
    href: (
      import.meta.env.VITE_YOUTUBE_URL || "https://www.youtube.com/@naseeb_edu"
    ).trim(),
  },
];

function BrandLogo({ className = "" }) {
  return (
    <span
      className={`brand-logo ${className}`}
      role="img"
      aria-label={t("Naseeb Edu")}
    />
  );
}

function BrandLockup() {
  return (
    <div className="brand-lockup">
      <BrandLogo />
      <div>
        <b>{t("Naseeb Edu")}</b>
        <small>{t("Education Counseling Platform")}</small>
      </div>
    </div>
  );
}

function LanguageSelector({ language, onChange }) {
  return (
    <label className="language-selector compact" aria-label={t("Language")}>
      <Globe2 size={15} />
      <select
        value={language}
        onChange={(event) => onChange(event.target.value)}
      >
        {LANGUAGE_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.short}
          </option>
        ))}
      </select>
    </label>
  );
}

function ThemeToggle({ theme, onToggle }) {
  const isDark = theme === "dark";
  return (
    <button
      type="button"
      className="icon-button theme-toggle"
      onClick={onToggle}
      title={isDark ? t("Light mode") : t("Dark mode")}
      aria-label={isDark ? t("Switch to light mode") : t("Switch to dark mode")}
      aria-pressed={isDark}
    >
      {isDark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}

export default function LandingPage({
  onLogin,
  theme,
  toggleTheme,
  language,
  changeLanguage,
}) {
  const pageRef = useRef(null);
  const railRef = useRef(null);
  /* The rail is scrolled, never paginated, so its controls are derived from the
     scroll position rather than from an index the component owns — a touch
     swipe and an arrow press then agree about which end has been reached. */
  const [railEdges, setRailEdges] = useState({ atStart: true, atEnd: false });
  /* One answer open at a time: nine questions stacked open would bury the
     closing call to action under a wall of prose. The first is open on load
     so the section reads as answers rather than as a row of shut drawers. */
  const [openFaq, setOpenFaq] = useState(FAQS[0]?.id || "");
  const path = [
    {
      title: "Set the direction",
      description:
        "Turn a student’s goals into a focused university and scholarship strategy.",
    },
    {
      title: "Build the profile",
      description:
        "Academics, activities, honors and documents collected in one verified profile.",
    },
    {
      title: "Prepare applications",
      description:
        "Tasks, essays, recommendations and deadlines, each with a clear owner.",
    },
    {
      title: "Make the decision",
      description:
        "Compare offers, funding and fit, then commit to the right final choice.",
    },
  ];
  const capabilities = [
    {
      icon: Compass,
      title: "Roadmap",
      description:
        "Level-linked missions a teacher or counselor approves, so progress is earned rather than claimed.",
      note: "Staff approved",
    },
    {
      icon: GraduationCap,
      title: "College Search",
      description:
        "Universities ranked against the student’s real GPA, SAT, IELTS, budget and scholarship needs.",
      note: "Profile driven",
    },
    {
      icon: PenLine,
      title: "Essay Lab",
      description:
        "Drafts, revision history and counselor feedback stay with the application they belong to.",
      note: "Versioned",
    },
    {
      icon: FileText,
      title: "Documents",
      description:
        "Transcripts, certificates and evidence stream through authenticated links, never public URLs.",
      note: "Private storage",
    },
    {
      icon: MessageSquareText,
      title: "Messaging",
      description:
        "Direct, group and school channels, with moderation and reporting built in.",
      note: "Moderated",
    },
    {
      icon: ClipboardCheck,
      title: "Student 360",
      description:
        "One reviewable view per student for staff — with private notes and drafts deliberately excluded.",
      note: "Audited",
    },
  ];
  const ledger = [
    {
      figure: 6,
      label: "Roles",
      description:
        "Admin, counselor, teacher, school, student and parent — each with its own data scope.",
    },
    {
      figure: 3,
      label: "Languages",
      description:
        "Uzbek, Russian and English across the whole product, not just the marketing page.",
    },
    {
      figure: 0,
      label: "Public sign-ups",
      description:
        "Accounts are issued by a school or counselor. Nobody can register their way into student data.",
    },
  ];
  const aboutPrinciples = [
    {
      title: "Built for international applications",
      description:
        "Designed for students, counselors and schools navigating universities across borders.",
    },
    {
      title: "Human guidance, supported by software",
      description:
        "The platform organizes progress and evidence; counselors keep every decision personal.",
    },
    {
      title: "From first plan to final offer",
      description:
        "Goals, documents, applications and outcomes stay connected across the whole journey.",
    },
  ];
  const connectedRoles = [
    { icon: Building2, label: "Schools" },
    { icon: UserRoundCheck, label: "Counselors" },
    { icon: GraduationCap, label: "Students" },
    { icon: Presentation, label: "Teachers" },
    { icon: HeartHandshake, label: "Parents" },
    { icon: ShieldCheck, label: "Admins" },
  ];
  const hasPlacements = PLACEMENT_ROWS.length > 0;
  const hasTeam = TEAM.length > 0;
  const hasReviews = STUDENT_REVIEWS.length > 0;
  /* The footer follows the three-column reference: product paths, information
     and social channels. Contact details sit together on the legal line below
     rather than becoming a fourth, visually unrelated column. */
  const footerColumns = [
    {
      title: "Platform",
      links: [
        { label: "Journey", href: "#journey" },
        { label: "Platform", href: "#platform" },
      ],
    },
    {
      title: "Information",
      links: [
        { label: "About us", href: "#about" },
        ...(hasTeam ? [{ label: "Team", href: "#team" }] : []),
        ...(hasReviews ? [{ label: "Stories", href: "#reviews" }] : []),
        { label: "FAQ", href: "#faq" }
      ],
    },
    {
      title: "Social media",
      links: SOCIAL_LINKS,
    },
  ];

  /* One card per press, measured from the two cards themselves so the step
     always includes the real gap — no duplicated width constant to keep in
     sync with the four breakpoints the rail is retuned at. */
  const scrollRailBy = (direction) => {
    const rail = railRef.current;
    if (!rail) return;
    const [first, second] = rail.children;
    const step = second
      ? second.offsetLeft - first.offsetLeft
      : rail.clientWidth;
    const reduced = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    rail.scrollBy({
      left: direction * step,
      behavior: reduced ? "auto" : "smooth",
    });
  };

  useEffect(() => {
    const page = pageRef.current;
    if (!page) return undefined;
    const reduced = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    const paths = [...page.querySelectorAll(".landing-path-list")];
    const steps = [...page.querySelectorAll(".landing-path-list li")];
    const groups = [...page.querySelectorAll("[data-reveal]")];
    const navLinks = [...page.querySelectorAll(".landing-nav nav a")];
    const navTargets = navLinks.map((link) =>
      page.querySelector(link.getAttribute("href")),
    );
    const rail = railRef.current;
    if (!reduced) page.classList.add("is-animated");

    /* Reveals are observed, not scroll-computed. A scroll listener only fires
       when the user scrolls: an instant jump, a restored scroll position, a
       resize that moves a section into view or a stalled frame all leave the
       section stuck at opacity 0 with nothing to un-stick it. That is how the
       dashboards ended up invisible. The observer fires on layout, and if it
       is unavailable everything is revealed outright — content must never be
       hidden by a decoration that might not run. */
    const revealTargets = [...groups, ...paths];
    let observer = null;
    if ("IntersectionObserver" in window) {
      observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              /* Already on screen on the observer's first pass: reveal it
               without ever arming it, so above-the-fold copy cannot flash. */
              entry.target.classList.remove("is-armed");
              entry.target.classList.add("is-in");
              observer.unobserve(entry.target);
            } else {
              entry.target.classList.add("is-armed");
            }
          });
        },
        { rootMargin: "0px 0px -10% 0px" },
      );
      revealTargets.forEach((target) => observer.observe(target));
    }
    let frame = 0;

    const update = () => {
      frame = 0;
      const viewport = window.innerHeight;
      page.classList.toggle("is-scrolled", window.scrollY > 24);
      page.classList.toggle("is-compact", window.scrollY > viewport * 0.6);
      if (steps.length) {
        let nearest = 0;
        let shortestDistance = Infinity;
        steps.forEach((step, index) => {
          const distance = Math.abs(
            step.getBoundingClientRect().top - viewport * 0.38,
          );
          if (distance < shortestDistance) {
            nearest = index;
            shortestDistance = distance;
          }
        });
        steps.forEach((step, index) =>
          step.classList.toggle("is-active", index === nearest),
        );
      }
      let current = -1;
      navTargets.forEach((section, index) => {
        if (section && section.getBoundingClientRect().top <= viewport * 0.38)
          current = index;
      });
      navLinks.forEach((link, index) => {
        if (index === current) link.setAttribute("aria-current", "true");
        else link.removeAttribute("aria-current");
      });
    };
    /* Deliberately not rAF-throttled like the page-scroll work above it. That
       pattern writes classes on every frame, where a frame budget is the point;
       this one derives two booleans, so throttling to a frame would still hand
       React a fresh object 60 times a second and re-render the whole page for
       it. Bailing out unless an edge is actually crossed is the cheaper trade:
       three cached layout reads per scroll event, and a re-render only twice
       across a full traverse of the rail. */
    const syncRail = () => {
      if (!rail) return;
      /* A 2px tolerance: fractional layout widths mean scrollLeft rarely lands
         exactly on the maximum, which would leave "next" live at the end. */
      const remaining = rail.scrollWidth - rail.clientWidth - rail.scrollLeft;
      const atStart = rail.scrollLeft <= 2;
      const atEnd = remaining <= 2;
      setRailEdges((current) =>
        current.atStart === atStart && current.atEnd === atEnd
          ? current
          : { atStart, atEnd },
      );
    };
    const onChange = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };
    /* Resizing changes how many cards fit, so the arrows have to be re-derived
       on resize as well as on scroll — otherwise a rail that stops overflowing
       keeps a live "next" arrow that does nothing. */
    const onResize = () => {
      onChange();
      syncRail();
    };
    update();
    syncRail();
    window.addEventListener("scroll", onChange, { passive: true });
    window.addEventListener("resize", onResize, { passive: true });
    rail?.addEventListener("scroll", syncRail, { passive: true });
    return () => {
      window.removeEventListener("scroll", onChange);
      window.removeEventListener("resize", onResize);
      rail?.removeEventListener("scroll", syncRail);
      observer?.disconnect();
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <div className="landing-page" id="landing-top" ref={pageRef}>
      <a className="landing-skip" href="#landing-main">
        {t("Skip to content")}
      </a>
      <header className="landing-nav">
        <div className="lp-shell">
          <a
            href="#landing-top"
            className="landing-brand"
            aria-label={t("Naseeb Edu home")}
          >
            <BrandLockup />
          </a>
          <nav aria-label={t("Landing navigation")}>
            <a href="#journey">{t("Journey")}</a>
            <a href="#platform">{t("Platform")}</a>
            <a href="#about">{t("About us")}</a>
            {hasReviews && <a href="#reviews">{t("Stories")}</a>}
            <a href="#faq">{t("FAQ")}</a>
          </nav>
          <div className="landing-nav-actions">
            <LanguageSelector language={language} onChange={changeLanguage} />
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
            <button
              type="button"
              className="landing-login-button"
              onClick={onLogin}
            >
              {t("Sign in")}
            </button>
          </div>
        </div>
      </header>

      <main id="landing-main">
        <section className="landing-hero">
          <HeroParticleNetwork theme={theme} />
          <div className="lp-shell landing-hero-grid">
            <div className="landing-hero-copy">
              <p className="lp-eyebrow">
                {t("For schools, counselors and students in Uzbekistan")}
              </p>
              <h1>
                <span>{t("The application")}</span>{" "}
                <span>{t("is a long year.")}</span>{" "}
                <em>{t("Hold it together.")}</em>
              </h1>
              <p className="landing-hero-lede">
                {t(
                  "One workspace where a school, a counselor and a student run an international university application together — from the first goal to the final offer.",
                )}
              </p>
              <div className="landing-hero-actions">
                <a className="landing-primary-cta" href="#journey">
                  {t("See how it works")} <ChevronRight size={17} />
                </a>
              </div>
            </div>
            <figure className="landing-hero-media">
              <img
                src="/landing/naseeb-counseling-hero-v2.jpg"
                alt={t(
                  "A student and counselor planning a university application together.",
                )}
                width="1717"
                height="916"
                decoding="async"
              />
            </figure>
          </div>
          <div className="landing-rail">
            <div className="lp-shell">
              {ledger.map((item) => (
                <article key={item.label}>
                  <b>{formatNumberLocale(item.figure)}</b>
                  <span>{t(item.label)}</span>
                  <small>{t(item.description)}</small>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section
          className={`landing-role-strip ${hasPlacements ? "landing-placement-strip" : ""}`}
          aria-labelledby={
            hasPlacements
              ? PLACEMENT_ROWS.map(({ id }) => `placement-${id}-title`).join(
                  " ",
                )
              : "connected-roles-title"
          }
        >
          {hasPlacements ? (
            PLACEMENT_ROWS.map(({ id, title, directory, entries }, row) => (
              <div className="landing-placement-row" key={id}>
                <p id={`placement-${id}-title`}>{t(title)}</p>
                <ul
                  className="landing-role-accessible"
                  aria-labelledby={`placement-${id}-title`}
                >
                  {entries.map(({ name }) => (
                    <li key={name}>{name}</li>
                  ))}
                </ul>
                <div
                  className="landing-role-marquee landing-logo-marquee"
                  role="region"
                  aria-labelledby={`placement-${id}-title`}
                  tabIndex={0}
                >
                  <div
                    className={`landing-role-track landing-role-track-${row + 1}`}
                    style={{
                      "--lp-marquee-duration": `${entries.length * 4.5}s`,
                    }}
                    aria-hidden="true"
                  >
                    {[...entries, ...entries].map(
                      ({ name, file, label, caption, tone, layout }, index) => (
                        <span
                          key={`${id}-${name}-${index}`}
                          title={name}
                          className={
                            layout === "lockup"
                              ? "landing-placement-lockup"
                              : undefined
                          }
                          data-marquee-copy={
                            index >= entries.length ? "true" : undefined
                          }
                        >
                          {file ? (
                            <>
                              <img
                                className={
                                  [
                                    tone === "light" &&
                                      "landing-placement-logo-inverse",
                                    tone === "original" &&
                                      "landing-placement-logo-original",
                                    layout === "square" &&
                                      "landing-placement-logo-square",
                                    layout === "tall" &&
                                      "landing-placement-logo-tall",
                                    label && "landing-placement-logo-icon",
                                  ]
                                    .filter(Boolean)
                                    .join(" ") || undefined
                                }
                                src={`/landing/${directory}/${file}`}
                                alt=""
                                decoding="async"
                              />
                              {label ? (
                                <b className="landing-placement-name">
                                  {label}
                                  {caption ? <small>{caption}</small> : null}
                                </b>
                              ) : null}
                            </>
                          ) : (
                            <b className="landing-placement-name">
                              {label || name}
                            </b>
                          )}
                        </span>
                      ),
                    )}
                  </div>
                </div>
              </div>
            ))
          ) : (
            <>
              <p id="connected-roles-title">
                {t("One workspace, every role connected")}
              </p>
              <ul className="landing-role-accessible">
                {connectedRoles.map(({ label }) => (
                  <li key={label}>{t(label)}</li>
                ))}
              </ul>
              <div className="landing-role-marquee" aria-hidden="true">
                {[0, 1].map((row) => (
                  <div
                    className={`landing-role-track landing-role-track-${row + 1}`}
                    key={row}
                  >
                    {[...connectedRoles, ...connectedRoles].map(
                      ({ icon: Icon, label }, index) => (
                        <span key={`${row}-${label}-${index}`}>
                          <Icon size={27} aria-hidden="true" />
                          {t(label)}
                        </span>
                      ),
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </section>

        <section className="landing-band landing-journey" id="journey">
          <div className="lp-shell">
            <div className="landing-journey-grid">
              <div className="landing-section-head" data-reveal>
                <h2>{t("Four steps, in order.")}</h2>
                <p>
                  {t(
                    "The application journey moves through four clear stages.",
                  )}
                </p>
              </div>
              <ol className="landing-path-list">
                {path.map((step) => (
                  <li key={step.title}>
                    <h3>{t(step.title)}</h3>
                    <p>{t(step.description)}</p>
                  </li>
                ))}
              </ol>
              <figure className="landing-specimen">
                <figcaption>
                  {t("Step 3")} · {t("Applications")}
                </figcaption>
                <p>{t("Build a balanced university shortlist")}</p>
                <div>
                  <span className="landing-specimen-status">
                    {t("Submitted for approval")}
                  </span>
                  <b>{tx`+${formatNumberLocale(75)} XP`}</b>
                </div>
                <small>
                  {t(
                    "The next step stays locked until a counselor approves this one. XP counts toward the student’s level.",
                  )}
                </small>
              </figure>
            </div>
            <div
              className="landing-product-showcase landing-student-showcase"
              data-reveal
            >
              <div className="landing-showcase-copy">
                <p className="lp-eyebrow">{t("For students")}</p>
                <h3>{t("Know what comes next.")}</h3>
              </div>
              <p className="landing-showcase-note">
                {t(
                  "Follow your roadmap, prepare each application and ask for help before a deadline becomes a problem.",
                )}
              </p>
              <StudentDashboardPreview />
            </div>
          </div>
        </section>

        <section className="landing-band landing-platform" id="platform">
          <div className="lp-shell">
            <div className="landing-section-head" data-reveal>
              <h2>{t("What the workspace actually does.")}</h2>
              <p>{t("Six connected surfaces, not six separate tools.")}</p>
            </div>
            <div className="landing-register">
              {capabilities.map(({ icon: Icon, title, description, note }) => (
                <article className="landing-capability" key={title}>
                  <Icon size={19} aria-hidden="true" />
                  <h3>{t(title)}</h3>
                  <p>{t(description)}</p>
                  <span className="landing-capability-note">{t(note)}</span>
                </article>
              ))}
            </div>
            <div
              className="landing-product-showcase landing-counselor-showcase"
              data-reveal
            >
              <div className="landing-showcase-copy">
                <p className="lp-eyebrow">{t("For counselors")}</p>
                <h3>{t("Every student, one clear view.")}</h3>
              </div>
              <p className="landing-showcase-note">
                {t(
                  "See progress, deadlines and submitted work without losing the person behind the application.",
                )}
              </p>
              <CounselorDashboardPreview />
            </div>
          </div>
        </section>

        <section className="landing-band landing-about" id="about">
          <div className="lp-shell landing-about-grid">
            <header className="landing-about-head" data-reveal>
              <p className="lp-eyebrow">{t("About Naseeb Edu")}</p>
              <h2>
                {t(
                  "Guidance works better when everyone works from the same record.",
                )}
              </h2>
              <p>
                {t(
                  "Naseeb Edu is an education counseling platform built for schools, counselors, students and families navigating international university applications from Uzbekistan.",
                )}
              </p>
            </header>
            <dl className="landing-about-principles" data-reveal>
              {aboutPrinciples.map((item, index) => (
                <div key={item.title}>
                  <span aria-hidden="true">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <dt>{t(item.title)}</dt>
                  <dd>{t(item.description)}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        {hasTeam && (
          <section className="landing-band landing-team" id="team">
            <div className="lp-shell">
              <header className="landing-team-head">
                <h2>{t("Big Five")}</h2>
              </header>

              <ul className="landing-team-grid">
                {TEAM.map((member) => (
                  <li className="landing-team-card" key={member.id}>
                    <div className="landing-team-portrait">
                      {member.photo ? (
                        <img
                          src={`/landing/team/${member.photo}`}
                          alt=""
                          loading="lazy"
                          decoding="async"
                        />
                      ) : (
                        <span
                          className="landing-team-monogram"
                          aria-hidden="true"
                        >
                          {member.initials}
                        </span>
                      )}
                    </div>
                    <a
                      className="landing-team-email"
                      href={`mailto:${member.email}`}
                    >
                      {member.email}
                    </a>
                    <b>{member.name}</b>
                    <span className="landing-team-role">{t(member.role)},</span>
                    <span className="landing-team-note">{t(member.note)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </section>
        )}

        {hasReviews && (
          <section className="landing-band landing-reviews" id="reviews">
            <div className="lp-shell">
              <header className="landing-reviews-head" data-reveal>
                <p className="lp-eyebrow">{t("Student stories")}</p>
                <div className="landing-reviews-title">
                  <div>
                    <h2>{t("Hear from our students.")}</h2>
                    <p>
                      {t(
                        "How students describe running an application inside Naseeb Edu.",
                      )}
                    </p>
                  </div>
                </div>
              </header>
            </div>

            {STUDENT_REVIEWS.length > 1 && (
              <div className="landing-reviews-controls">
                <button
                  type="button"
                  aria-label={t("Previous stories")}
                  disabled={railEdges.atStart}
                  onClick={() => scrollRailBy(-1)}
                >
                  <ArrowLeft size={18} aria-hidden="true" />
                </button>
                <button
                  type="button"
                  aria-label={t("More stories")}
                  disabled={railEdges.atEnd}
                  onClick={() => scrollRailBy(1)}
                >
                  <ArrowRight size={18} aria-hidden="true" />
                </button>
              </div>
            )}

            <ul
              className="landing-story-rail"
              role="group"
              aria-label={t("Student stories")}
              ref={railRef}
            >
              {STUDENT_REVIEWS.map((review) => (
                <li className="landing-story-card" key={review.id}>
                  <header className="landing-review-person">
                    <span className="landing-story-avatar" aria-hidden="true">
                      {review.photo ? (
                        <img
                          src={`/landing/reviews/${review.photo}`}
                          alt=""
                          loading="lazy"
                          decoding="async"
                        />
                      ) : (
                        review.initials
                      )}
                    </span>
                    <span>
                      <b>{review.name}</b>
                    </span>
                  </header>
                  {(review.university || review.scholarship) && (
                    <div className="landing-review-meta">
                      {review.university && (
                        <p>
                          <GraduationCap size={19} aria-hidden="true" />
                          <span>{review.university}</span>
                        </p>
                      )}
                      {review.scholarship && (
                        <p>
                          <CircleDollarSign size={18} aria-hidden="true" />
                          <span>
                            {t("Scholarship")}: {review.scholarship}
                          </span>
                        </p>
                      )}
                    </div>
                  )}
                  <blockquote>
                    <p>{t(review.quote)}</p>
                  </blockquote>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="landing-band landing-faq" id="faq">
          <div className="lp-shell landing-faq-grid">
            <header className="landing-faq-head" data-reveal>
              <p className="lp-eyebrow">{t("Frequently asked questions")}</p>
              <h2>{t("What schools and students ask before they start.")}</h2>
              <p>
                {t(
                  "What the platform does, who it is for, and what it takes for a school to begin.",
                )}
              </p>
            </header>

            <div className="landing-faq-list" data-reveal>
              {FAQS.map((item) => {
                const isOpen = openFaq === item.id;
                return (
                  <div
                    className={`landing-faq-item ${isOpen ? "is-open" : ""}`}
                    key={item.id}
                  >
                    <h3>
                      <button
                        type="button"
                        className="landing-faq-trigger"
                        id={`${item.id}-question`}
                        aria-expanded={isOpen}
                        aria-controls={`${item.id}-answer`}
                        onClick={() => setOpenFaq(isOpen ? "" : item.id)}
                      >
                        <span>{t(item.question)}</span>
                        <span className="landing-faq-mark" aria-hidden="true" />
                      </button>
                    </h3>
                    <div
                      className="landing-faq-answer"
                      id={`${item.id}-answer`}
                      role="region"
                      aria-labelledby={`${item.id}-question`}
                    >
                      <div>
                        {item.answer.map((paragraph) => (
                          <p key={paragraph}>{t(paragraph)}</p>
                        ))}
                        {item.contact && (
                          <a
                            className="landing-text-cta landing-faq-contact"
                            href={`mailto:${SUPPORT_EMAIL}`}
                          >
                            <Mail size={16} aria-hidden="true" />
                            {SUPPORT_EMAIL}
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <section className="landing-closing">
          <div className="lp-shell" data-reveal>
            <h2>{t("Bring every application into one clear workspace.")}</h2>
            <p>
              {t(
                "Give counselors and students one shared place to plan, review and move forward.",
              )}
            </p>
            <div className="landing-closing-actions">
              {BOOK_MEETING_URL ? (
                <a className="landing-primary-cta" href={BOOK_MEETING_URL}>
                  {t('Book a call')} <ChevronRight size={17} />
                </a>
              ) : (
                <button type="button" className="landing-primary-cta" disabled>
                  {t('Book a call')} <ChevronRight size={17} />
                </button>
              )}
            </div>
          </div>
        </section>
      </main>

      <footer className="landing-footer">
        <div className="lp-shell landing-footer-grid">
          {footerColumns.map((column) => (
            <nav
              className="landing-footer-links"
              key={column.title}
              aria-label={t(column.title)}
            >
              <span>{t(column.title)}</span>
              {column.links.map((link) =>
                link.action ? (
                  <button type="button" onClick={link.action} key={link.label}>
                    {t(link.label)}
                  </button>
                ) : (
                  <a
                    href={link.href}
                    key={link.label}
                    target={
                      link.href?.startsWith("http") ? "_blank" : undefined
                    }
                    rel={
                      link.href?.startsWith("http") ? "noreferrer" : undefined
                    }
                  >
                    {t(link.label)}
                  </a>
                ),
              )}
            </nav>
          ))}
        </div>
        <div className="lp-shell landing-footer-legal">
          {/* Two lines rather than one chain of dot-separated fragments: the
              things a visitor can act on read first, and the imprint sits under
              them as a single quiet sentence. */}
          <div className="landing-footer-imprint">
            <p className="landing-footer-contact">
              <a href={`tel:${CONTACT_PHONE.replace(/[^+\d]/g, "")}`}>
                {CONTACT_PHONE}
              </a>
              <span aria-hidden="true">·</span>
              <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>
              {SCHOOL_CONTACT_URL && (
                <>
                  <span aria-hidden="true">·</span>
                  <a href={SCHOOL_CONTACT_URL}>{t("Contact our team")}</a>
                </>
              )}
            </p>
            <small>
              © {new Date().getFullYear()} Naseeb Edu, {CONTACT_LOCATION}.{" "}
              {t("All rights reserved.")}
            </small>
          </div>
          <a
            className="landing-footer-top"
            href="#landing-top"
            aria-label={t("Back to top")}
            title={t("Back to top")}
          >
            <ArrowUp size={16} aria-hidden="true" />
          </a>
        </div>
        {/* The wordmark is the sign-off, not a heading: it carries no
            information the columns above have not already given, so it is
            hidden from assistive technology and lets the band end on the
            brand instead of on a rule. */}
        <p className="landing-footer-wordmark" aria-hidden="true">
          {t("Naseeb Edu")}
        </p>
      </footer>
    </div>
  );
}
