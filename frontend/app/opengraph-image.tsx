import { ImageResponse } from "next/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "GhostRep — Your best rep becomes your coach.";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "80px",
          background: "linear-gradient(160deg, #07090c 0%, #10161c 55%, #0b1210 100%)",
          color: "#F3F5F7",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 22 }}>
          <svg width="84" height="84" viewBox="0 0 64 64">
            <g fill="none" strokeLinecap="round" strokeLinejoin="round">
              <path
                d="M47.2 20.6 A18.6 18.6 0 1 0 47.2 43.8 V32 H30"
                stroke="#FF8A3D"
                strokeWidth="7.1"
                opacity="0.92"
                transform="translate(3.6 4.2)"
              />
              <path d="M47.2 20.6 A18.6 18.6 0 1 0 47.2 43.8 V32 H30" stroke="#20D6C7" strokeWidth="7.4" />
            </g>
          </svg>
          <div style={{ display: "flex", fontSize: 56, fontWeight: 700, letterSpacing: -2 }}>
            Ghost<span style={{ color: "#20D6C7" }}>Rep</span>
          </div>
        </div>
        <div style={{ display: "flex", marginTop: 36, fontSize: 44, fontWeight: 600, letterSpacing: -1.4, maxWidth: 820 }}>
          Your best rep becomes your coach.
        </div>
        <div style={{ display: "flex", marginTop: 18, fontSize: 24, color: "#9AA3B0", maxWidth: 720 }}>
          See your movement. Understand your progress.
        </div>
      </div>
    ),
    size,
  );
}
