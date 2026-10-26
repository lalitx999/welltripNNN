/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./apps/**/templates/**/*.html",
    "./apps/**/*.py",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Kanit", "Inter", "sans-serif"],
        display: ["Kanit", "Inter", "sans-serif"],
      },
      colors: {
        forest: {
          DEFAULT: "#193E30",
          50: "#F2F7F4",
          100: "#E2EDE6",
          200: "#C4DBD0",
          300: "#99C0AD",
          400: "#5D9B7B",
          500: "#27543E",
          600: "#1E4431",
          700: "#183728",
          800: "#193E30",
          900: "#12291E",
          950: "#0B1A13",
          dark: "#1F2925",
        },
        gold: {
          DEFAULT: "#C5A059",
          50: "#FAF6ED",
          100: "#F3EBD6",
          200: "#E7D6AC",
          300: "#D6BF84",
          400: "#CEAF6C",
          500: "#C5A059",
          600: "#A8833D",
          700: "#84652B",
          800: "#634B20",
          900: "#443216",
        },
        cream: {
          DEFAULT: "#FAF9F6",
          50: "#FFFFFF",
          100: "#FAF9F6",
          200: "#F4EFE6",
          300: "#EAE3D5",
          400: "#DDD4C3",
          500: "#C5B8A3",
        },
        earth: {
          DEFAULT: "#111827",
          500: "#6E6862",
          800: "#26221F",
          900: "#111827",
        },
        surface: "#FFFFFF",
      },
      borderRadius: {
        'luxury': '24px',
        '2xl': '1rem',
        '3xl': '1.5rem',
      },
    },
  },
  plugins: [],
}
