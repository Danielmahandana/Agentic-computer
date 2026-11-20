export function SeedlingMark({ className = '' }: { className?: string }) {
  return (
    <svg
      className={`seedling-mark ${className}`}
      viewBox="0 0 52 52"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M26 3.8c12.4 0 22.2 9.8 22.2 22.1S38.4 48.2 26 48.2 3.8 38.3 3.8 25.9 13.6 3.8 26 3.8Z"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeDasharray="2 2.2"
      />
      <path
        d="M26.1 39.5c-.2-8.1.1-15.3.8-21.8m-.1 10.1c-4.8-.2-8.1-2.7-9.2-7.3 5.2-.5 8.5 2 9.2 7.3Zm.4-5.7c.5-4.8 3.5-7.7 8.4-8-0.1 5.2-3 8-8.4 8Zm-8.7 10.2c2.6.1 4.9 1.2 6.8 3.3"
        stroke="currentColor"
        strokeWidth="1.55"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M21 39.4h10.2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  )
}

export function AgentTerrariumIllustration() {
  return (
    <svg
      className="terrarium-art"
      viewBox="0 0 520 270"
      fill="none"
      aria-hidden="true"
    >
      <defs>
        <radialGradient id="sunGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#d9a441" stopOpacity="0.34" />
          <stop offset="65%" stopColor="#d9a441" stopOpacity="0.08" />
          <stop offset="100%" stopColor="#d9a441" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="mossWash" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#4a6b57" stopOpacity="0.16" />
          <stop offset="100%" stopColor="#31493c" stopOpacity="0.04" />
        </linearGradient>
        <linearGradient id="clayAccent" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#c15b3f" stopOpacity="0.22" />
          <stop offset="100%" stopColor="#d9a441" stopOpacity="0.1" />
        </linearGradient>
      </defs>

      {/* Ambient warm sun & orbital arcs */}
      <circle cx="382" cy="78" r="68" fill="url(#sunGlow)" className="art-breathe" />
      <circle cx="382" cy="78" r="24" fill="#d9a441" fillOpacity="0.22" stroke="#d9a441" strokeWidth="1.2" />
      <ellipse
        cx="260"
        cy="142"
        rx="214"
        ry="96"
        stroke="#4a6b57"
        strokeOpacity="0.22"
        strokeWidth="1.1"
        strokeDasharray="4 6"
        className="art-orbit"
      />
      <ellipse
        cx="260"
        cy="142"
        rx="168"
        ry="72"
        stroke="#c15b3f"
        strokeOpacity="0.18"
        strokeWidth="1"
        strokeDasharray="2 5"
      />

      {/* Botanical leaves behind the browser frame */}
      <g className="art-sway-left">
        <path
          d="M112 214c-18-36-22-74-6-114 26 24 38 56 34 96"
          fill="url(#mossWash)"
          stroke="#4a6b57"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
        <path
          d="M112 214c-6-32-6-64 4-96"
          stroke="#4a6b57"
          strokeOpacity="0.55"
          strokeWidth="1.1"
          strokeLinecap="round"
        />
        <path
          d="M92 204c-32-22-48-48-48-80 28 6 48 24 58 54"
          fill="url(#mossWash)"
          stroke="#4a6b57"
          strokeWidth="1.25"
          strokeLinecap="round"
        />
      </g>

      <g className="art-sway-right">
        <path
          d="M408 214c22-34 28-68 18-106-28 20-42 48-42 86"
          fill="url(#clayAccent)"
          stroke="#c15b3f"
          strokeOpacity="0.65"
          strokeWidth="1.35"
          strokeLinecap="round"
        />
        <path
          d="M424 202c26-14 44-34 50-62-26 2-46 16-58 40"
          fill="url(#mossWash)"
          stroke="#4a6b57"
          strokeWidth="1.2"
          strokeLinecap="round"
        />
      </g>

      {/* Rounded organic browser window */}
      <g className="art-float">
        <rect
          x="138"
          y="54"
          width="244"
          height="154"
          rx="28"
          fill="#fbf8f2"
          stroke="#2b241e"
          strokeOpacity="0.18"
          strokeWidth="1.5"
        />
        <path
          d="M138 90h244"
          stroke="#2b241e"
          strokeOpacity="0.1"
          strokeWidth="1.2"
        />
        {/* Traffic dots */}
        <circle cx="164" cy="72" r="4" fill="#c15b3f" fillOpacity="0.65" />
        <circle cx="178" cy="72" r="4" fill="#d9a441" fillOpacity="0.7" />
        <circle cx="192" cy="72" r="4" fill="#4a6b57" fillOpacity="0.65" />
        {/* Rounded address pill */}
        <rect
          x="210"
          y="64"
          width="146"
          height="16"
          rx="8"
          fill="#efe8dc"
        />

        {/* Inside browser: structured observation blocks */}
        <rect x="160" y="106" width="118" height="22" rx="11" fill="#efe8dc" stroke="#4a6b57" strokeOpacity="0.35" strokeWidth="1.1" />
        <rect x="286" y="106" width="72" height="22" rx="11" fill="#4a6b57" fillOpacity="0.88" />
        <path d="M306 117h32" stroke="#f7f3ec" strokeWidth="2" strokeLinecap="round" />

        {/* Result cards inside browser */}
        <rect x="160" y="140" width="94" height="50" rx="14" fill="#f7f3ec" stroke="#2b241e" strokeOpacity="0.12" strokeWidth="1.1" />
        <path d="M172 155h46M172 167h68M172 177h54" stroke="#4a6b57" strokeOpacity="0.45" strokeWidth="2" strokeLinecap="round" />

        <rect x="264" y="140" width="94" height="50" rx="14" fill="#f7f3ec" stroke="#2b241e" strokeOpacity="0.12" strokeWidth="1.1" />
        <path d="M276 155h42M276 167h66M276 177h48" stroke="#c15b3f" strokeOpacity="0.45" strokeWidth="2" strokeLinecap="round" />

        {/* Gliding semantic cursor badge */}
        <g className="art-cursor">
          <circle cx="316" cy="126" r="14" fill="#d9a441" fillOpacity="0.22" />
          <path
            d="M312 119l15 9-6.5 2.2-2.8 6.3-5.7-17.5Z"
            fill="#2b241e"
            stroke="#fbf8f2"
            strokeWidth="1.4"
            strokeLinejoin="round"
          />
        </g>
      </g>

      {/* Rolling ground contour lines */}
      <path
        d="M44 232c74-24 142-22 216 0 72 22 140 20 216-4"
        stroke="#4a6b57"
        strokeOpacity="0.3"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
      <path
        d="M78 248c62-16 122-14 182 2 64 16 124 14 182-6"
        stroke="#4a6b57"
        strokeOpacity="0.16"
        strokeWidth="1.1"
        strokeLinecap="round"
      />

      {/* Drifting botanical seeds */}
      <circle cx="88" cy="86" r="3" fill="#4a6b57" fillOpacity="0.45" className="art-seed-1" />
      <circle cx="446" cy="116" r="2.5" fill="#c15b3f" fillOpacity="0.5" className="art-seed-2" />
      <circle cx="156" cy="34" r="2.2" fill="#d9a441" fillOpacity="0.65" className="art-seed-2" />
      <circle cx="412" cy="48" r="2" fill="#4a6b57" fillOpacity="0.4" className="art-seed-1" />
    </svg>
  )
}

export function RadarCanopyIllustration() {
  return (
    <svg className="radar-art" viewBox="0 0 84 84" fill="none" aria-hidden="true">
      <circle cx="42" cy="42" r="36" stroke="#4a6b57" strokeOpacity="0.2" strokeWidth="1.2" strokeDasharray="3 4" className="art-spin-slow" />
      <circle cx="42" cy="42" r="24" stroke="#4a6b57" strokeOpacity="0.35" strokeWidth="1.2" />
      <circle cx="42" cy="42" r="12" fill="#4a6b57" fillOpacity="0.14" stroke="#4a6b57" strokeWidth="1.4" className="art-breathe" />
      <path d="M42 42L62 24" stroke="#c15b3f" strokeWidth="1.8" strokeLinecap="round" className="art-spin-sweep" />
      <circle cx="42" cy="42" r="3.5" fill="#31493c" />
    </svg>
  )
}

export function QuarantineSealMark() {
  return (
    <svg className="seal-mark" viewBox="0 0 36 36" fill="none" aria-hidden="true">
      <path
        d="M18 3l3.3 2.4 4.1-.4 1.8 3.7 3.7 1.8-.4 4.1L33 18l-2.4 3.3.4 4.1-3.7 1.8-1.8 3.7-4.1-.4L18 33l-3.3-2.4-4.1.4-1.8-3.7-3.7-1.8.4-4.1L3 18l2.4-3.3-.4-4.1 3.7-1.8 1.8-3.7 4.1.4L18 3Z"
        fill="#4a6b57"
        fillOpacity="0.14"
        stroke="#4a6b57"
        strokeWidth="1.25"
        strokeLinejoin="round"
      />
      <path
        d="M13 18.2l3.3 3.3 6.8-7"
        stroke="#31493c"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function HillsideDrawing() {
  return (
    <svg className="hillside-drawing" viewBox="0 0 700 320" fill="none" aria-hidden="true">
      <defs>
        <radialGradient id="hillSun" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#d9a441" stopOpacity="0.34" />
          <stop offset="100%" stopColor="#d9a441" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx="540" cy="86" r="76" fill="url(#hillSun)" className="art-breathe" />
      <circle cx="540" cy="86" r="22" stroke="#d9a441" strokeOpacity="0.6" strokeWidth="1.2" fill="#d9a441" fillOpacity="0.14" />
      <path d="M26 258c73-41 131-39 202-2 64 34 107 37 170 8 92-42 156-37 276 21" />
      <path d="M9 279c88-49 149-37 214 1 57 33 115 45 183 15 89-39 160-30 279 17" />
      <path d="M57 300c64-33 113-23 169 10 69 40 127 45 205 12 82-35 161-24 234 0" />
      <path d="M101 236c48-72 105-97 177-83 43 8 77 30 120 25 61-8 88-56 151-67 41-7 82 6 120 27" />
      <path d="M126 220c39-53 84-74 142-65 53 8 89 41 143 28 56-13 77-54 132-60 39-4 72 8 106 26" />
      <path d="M182 192c34-32 64-43 101-34 34 8 55 29 94 24 48-6 69-37 111-41 32-3 59 6 84 19" />
      <g className="art-sway-left">
        <path d="M327 148c-8-24-5-49 11-68m-8 60c-21-9-33-23-35-43 24 3 37 17 35 43Zm8-23c4-22 18-34 40-35-2 24-15 36-40 35Z" />
      </g>
      <g className="art-sway-right">
        <path d="M475 168c0-16 7-29 20-40m-18 33c-16-5-25-15-28-30 19 1 29 11 28 30Zm3-15c7-15 18-22 34-21-5 17-16 24-34 21Z" />
      </g>
      <circle cx="127" cy="96" r="2.4" fill="#4a6b57" fillOpacity="0.4" className="art-seed-1" />
      <circle cx="596" cy="116" r="2" fill="#c15b3f" fillOpacity="0.45" className="art-seed-2" />
      <circle cx="242" cy="74" r="1.8" fill="#d9a441" fillOpacity="0.55" className="art-seed-2" />
    </svg>
  )
}
