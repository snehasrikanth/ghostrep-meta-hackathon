import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0B0F14",
        }}
      >
        <svg width="128" height="128" viewBox="0 0 64 64">
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
      </div>
    ),
    size,
  );
}
