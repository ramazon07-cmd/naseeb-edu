import { ArrowUpRight } from 'lucide-react';

const CONTENT = {
  uz: {
    heading: ["Qiziqishlaringiz", "haqida bilib oling!"],
    description:
      "Kuchli tomonlaringizni aniqlang va shunga mos yo‘nalishni toping.",
    cta: "Sinab ko‘ring",
    time: "daqiqa",
    types: "xil obrazlar",
    free: "Test",
    access: "Mutlaqo Bepul",
    art: "O‘zini anglashni ifodalovchi oltin shisha va oq qatlamlardan tashkil topgan inson profili",
  },
  en: {
    heading: ["Learn about", "your interests!"],
    description:
      "Identify your strengths and find a direction that matches them.",
    cta: "Find your personality",
    time: "minutes",
    types: "distinct personalities",
    free: "Free",
    access: "personality test",
    art: "A layered ivory and amber glass profile representing self-discovery",
  },
  ru: {
    heading: ["Узнайте больше", "о своих интересах!"],
    description:
      "Определите свои сильные стороны и найдите подходящее направление.",
    cta: "Попробовать",
    time: "минут",
    types: "типов личности",
    free: "Тест",
    access: "абсолютно бесплатный",
    art: "Многослойный профиль из слоновой кости и янтарного стекла, символ самопознания",
  },
};

export default function MindSection({ language }) {
  const copy = CONTENT[language] || CONTENT.uz;
  return (
    <section className="landing-mind" id="naseeb-mind" aria-labelledby="naseeb-mind-title">
      <div className="lp-shell">
        <div className="landing-mind-panel" data-reveal>
          <div className="landing-mind-copy">
            <p className="landing-mind-brand"><img className="landing-mind-logo" src="/brand/naseeb-mind-logo.png" alt="" width="32" height="48" loading="lazy" decoding="async" /><span>Naseeb <b>Mind</b></span></p>
            <h2 id="naseeb-mind-title">{copy.heading[0]}<span>{copy.heading[1]}</span></h2>
            <p className="landing-mind-description">{copy.description}</p>
            <a className="landing-mind-cta" href="https://personality.naseebedu.com">{copy.cta}<ArrowUpRight size={20} aria-hidden="true" /></a>
          </div>
          <figure className="landing-mind-art">
            <img src="/landing/mind-self-discovery.webp" alt={copy.art} width="1536" height="1024" loading="lazy" decoding="async" />
            {/* Dark-mode twin, stacked on top and faded in by CSS. Both load with the card, so switching theme never waits on a download. */}
            <img className="landing-mind-art-dark" src="/landing/mind-self-discovery-dark.webp" alt="" aria-hidden="true" width="1536" height="1024" loading="lazy" decoding="async" />
          </figure>
          <dl className="landing-mind-facts">
            <div><dt>15</dt><dd>{copy.time}</dd></div>
            <div><dt>10</dt><dd>{copy.types}</dd></div>
            <div><dt>{copy.free}</dt><dd>{copy.access}</dd></div>
          </dl>
        </div>
      </div>
    </section>
  );
}
