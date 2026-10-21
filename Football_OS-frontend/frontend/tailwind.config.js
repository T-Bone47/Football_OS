/** @type {import('tailwindcss').Config} */
module.exports = {
    // `overline` is a Tailwind utility; without this an app's own eyebrow-label class draws a line above the text.
    blocklist: ["overline"],
    darkMode: ["class"],
    content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "./public/index.html"
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace']
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)'
      },
      colors: {
        // The product palette is defined once in src/styles/fio.css. Mapping the neutral
        // utilities (slate/gray) onto those tokens means existing route markup inherits the
        // same surfaces, hairlines and text hierarchy instead of running a second palette.
        slate: {
          50: 'rgb(var(--fio-n-50) / <alpha-value>)',
          100: 'rgb(var(--fio-n-100) / <alpha-value>)',
          200: 'rgb(var(--fio-n-200) / <alpha-value>)',
          300: 'rgb(var(--fio-n-300) / <alpha-value>)',
          400: 'rgb(var(--fio-n-400) / <alpha-value>)',
          500: 'rgb(var(--fio-n-500) / <alpha-value>)',
          600: 'rgb(var(--fio-n-600) / <alpha-value>)',
          700: 'rgb(var(--fio-n-700) / <alpha-value>)',
          800: 'rgb(var(--fio-n-800) / <alpha-value>)',
          900: 'rgb(var(--fio-n-900) / <alpha-value>)',
          950: 'rgb(var(--fio-n-950) / <alpha-value>)'
        },
        gray: {
          50: 'rgb(var(--fio-n-50) / <alpha-value>)',
          100: 'rgb(var(--fio-n-100) / <alpha-value>)',
          200: 'rgb(var(--fio-n-200) / <alpha-value>)',
          300: 'rgb(var(--fio-n-300) / <alpha-value>)',
          400: 'rgb(var(--fio-n-400) / <alpha-value>)',
          500: 'rgb(var(--fio-n-500) / <alpha-value>)',
          600: 'rgb(var(--fio-n-600) / <alpha-value>)',
          700: 'rgb(var(--fio-n-700) / <alpha-value>)',
          800: 'rgb(var(--fio-n-800) / <alpha-value>)',
          900: 'rgb(var(--fio-n-900) / <alpha-value>)',
          950: 'rgb(var(--fio-n-950) / <alpha-value>)'
        },
        emerald: {
          300: 'rgb(var(--fio-success) / <alpha-value>)',
          400: 'rgb(var(--fio-success) / <alpha-value>)',
          500: 'rgb(var(--fio-success) / <alpha-value>)'
        },
        amber: {
          300: 'rgb(var(--fio-warn) / <alpha-value>)',
          400: 'rgb(var(--fio-warn) / <alpha-value>)',
          500: 'rgb(var(--fio-warn) / <alpha-value>)'
        },
        red: {
          300: 'rgb(var(--fio-danger) / <alpha-value>)',
          400: 'rgb(var(--fio-danger) / <alpha-value>)',
          500: 'rgb(var(--fio-danger) / <alpha-value>)'
        },
        blue: {
          300: 'rgb(var(--fio-info) / <alpha-value>)',
          400: 'rgb(var(--fio-info) / <alpha-value>)',
          500: 'rgb(var(--fio-info) / <alpha-value>)'
        },
        purple: {
          300: 'rgb(var(--fio-model) / <alpha-value>)',
          400: 'rgb(var(--fio-model) / <alpha-value>)',
          500: 'rgb(var(--fio-model) / <alpha-value>)'
        },
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))'
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))'
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))'
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))'
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))'
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))'
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))'
        },
        // `--border` is a colour alias used directly by legacy route styles; the
        // Tailwind border token resolves to the same product hairline.
        border: 'var(--fio-line)',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        chart: {
          '1': 'hsl(var(--chart-1))',
          '2': 'hsl(var(--chart-2))',
          '3': 'hsl(var(--chart-3))',
          '4': 'hsl(var(--chart-4))',
          '5': 'hsl(var(--chart-5))'
        }
      },
      keyframes: {
        'accordion-down': {
          from: {
            height: '0'
          },
          to: {
            height: 'var(--radix-accordion-content-height)'
          }
        },
        'accordion-up': {
          from: {
            height: 'var(--radix-accordion-content-height)'
          },
          to: {
            height: '0'
          }
        }
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out'
      }
    }
  },
  plugins: [require("tailwindcss-animate")],
};