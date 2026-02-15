---
name: Frontend Pro Design
description: Professional frontend design system for creating stunning, modern web interfaces with premium aesthetics
---

# Frontend Pro Design Skill

## Overview
This skill provides comprehensive guidance for creating professional, visually stunning web interfaces that wow users at first glance. It covers modern design principles, color systems, typography, animations, and component patterns.

---

## 🎨 Core Design Principles

### 1. **Visual Hierarchy**
- Use size, color, and spacing to guide user attention
- Primary actions should be visually dominant
- Group related elements together
- Use whitespace generously (minimum 1.5-2rem between major sections)

### 2. **Premium Color Systems**
Never use basic colors (red, blue, green). Instead, use curated palettes:

```css
/* Modern Color Palette Examples */

/* Option 1: Vibrant Gradient System */
--primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
--accent-gradient: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
--success-gradient: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);

/* Option 2: Dark Mode Premium */
--bg-dark: #0f0f23;
--bg-card: #1a1a2e;
--accent-purple: #a855f7;
--accent-cyan: #06b6d4;
--text-primary: #f8fafc;
--text-secondary: #94a3b8;

/* Option 3: Light Mode Elegant */
--bg-light: #fafbfc;
--bg-card: #ffffff;
--primary-blue: #3b82f6;
--accent-indigo: #6366f1;
--text-dark: #1e293b;
--text-muted: #64748b;

/* Option 4: Warm & Inviting */
--warm-bg: #fff9f5;
--warm-card: #ffffff;
--warm-orange: #f97316;
--warm-amber: #f59e0b;
--warm-text: #292524;
```

### 3. **Brand Kits for Consistent Coloring**

**IMPORTANT**: When working on a project with an existing brand, ALWAYS use the brand's official colors instead of creating new ones. Brand consistency is critical for professional work.

#### How to Create a Brand Kit

**Step 1: Extract Brand Colors**
If you have a logo or existing brand materials:
- Use **Adobe Color** (color.adobe.com) to extract colors from images
- Use **ImageColorPicker.com** for quick color extraction
- Use browser DevTools to inspect existing website colors
- Check brand guidelines if available

**Step 2: Define Your Brand Kit**
Create a dedicated brand kit file or section:

```css
/* ========================================
   BRAND KIT - [Company Name]
   ======================================== */

:root {
  /* === PRIMARY BRAND COLORS === */
  --brand-primary: #your-primary-color;
  --brand-primary-light: #lighter-variant;
  --brand-primary-dark: #darker-variant;
  
  /* === SECONDARY BRAND COLORS === */
  --brand-secondary: #your-secondary-color;
  --brand-secondary-light: #lighter-variant;
  --brand-secondary-dark: #darker-variant;
  
  /* === ACCENT COLORS === */
  --brand-accent-1: #accent-color-1;
  --brand-accent-2: #accent-color-2;
  
  /* === NEUTRAL COLORS === */
  --brand-neutral-lightest: #f9fafb;
  --brand-neutral-light: #e5e7eb;
  --brand-neutral-medium: #9ca3af;
  --brand-neutral-dark: #374151;
  --brand-neutral-darkest: #111827;
  
  /* === SEMANTIC COLORS === */
  --brand-success: #10b981;
  --brand-warning: #f59e0b;
  --brand-error: #ef4444;
  --brand-info: #3b82f6;
}
```

#### Example Brand Kits

**Example 1: EzzyDelivery Qatar (Delivery Service)**
```css
:root {
  /* Primary - Energetic Orange/Red for speed and reliability */
  --ezzy-primary: #ff6b35;
  --ezzy-primary-light: #ff8c61;
  --ezzy-primary-dark: #e55a2b;
  
  /* Secondary - Professional Navy for trust */
  --ezzy-secondary: #1a2238;
  --ezzy-secondary-light: #2d3a5f;
  --ezzy-secondary-dark: #0d1120;
  
  /* Accent - Fresh Green for success/completion */
  --ezzy-accent: #4caf50;
  --ezzy-accent-light: #6fbf73;
  --ezzy-accent-dark: #3d8b40;
  
  /* Neutrals */
  --ezzy-bg: #f8f9fa;
  --ezzy-card: #ffffff;
  --ezzy-text: #1a2238;
  --ezzy-text-muted: #6c757d;
  
  /* Gradients */
  --ezzy-gradient-primary: linear-gradient(135deg, #ff6b35 0%, #f7931e 100%);
  --ezzy-gradient-success: linear-gradient(135deg, #4caf50 0%, #8bc34a 100%);
}
```

**Example 2: Tech Startup (Modern SaaS)**
```css
:root {
  /* Primary - Bold Purple for innovation */
  --startup-primary: #6366f1;
  --startup-primary-light: #818cf8;
  --startup-primary-dark: #4f46e5;
  
  /* Secondary - Vibrant Cyan for energy */
  --startup-secondary: #06b6d4;
  --startup-secondary-light: #22d3ee;
  --startup-secondary-dark: #0891b2;
  
  /* Accent - Electric Pink for highlights */
  --startup-accent: #ec4899;
  
  /* Dark Mode Colors */
  --startup-bg-dark: #0f172a;
  --startup-card-dark: #1e293b;
  --startup-text-dark: #f1f5f9;
  
  /* Gradients */
  --startup-gradient: linear-gradient(135deg, #6366f1 0%, #ec4899 100%);
  --startup-gradient-alt: linear-gradient(135deg, #06b6d4 0%, #6366f1 100%);
}
```

**Example 3: Luxury/Premium Brand**
```css
:root {
  /* Primary - Elegant Gold */
  --luxury-primary: #d4af37;
  --luxury-primary-light: #e5c158;
  --luxury-primary-dark: #b8941f;
  
  /* Secondary - Deep Charcoal */
  --luxury-secondary: #2c2c2c;
  --luxury-secondary-light: #3d3d3d;
  --luxury-secondary-dark: #1a1a1a;
  
  /* Accent - Rich Burgundy */
  --luxury-accent: #800020;
  
  /* Neutrals - Warm tones */
  --luxury-bg: #faf8f5;
  --luxury-card: #ffffff;
  --luxury-text: #2c2c2c;
  --luxury-text-muted: #6b6b6b;
}
```

**Example 4: Health/Wellness Brand**
```css
:root {
  /* Primary - Calming Teal */
  --wellness-primary: #14b8a6;
  --wellness-primary-light: #2dd4bf;
  --wellness-primary-dark: #0f766e;
  
  /* Secondary - Natural Green */
  --wellness-secondary: #84cc16;
  --wellness-secondary-light: #a3e635;
  --wellness-secondary-dark: #65a30d;
  
  /* Accent - Soft Lavender */
  --wellness-accent: #a78bfa;
  
  /* Neutrals - Soft and clean */
  --wellness-bg: #f0fdf4;
  --wellness-card: #ffffff;
  --wellness-text: #064e3b;
  --wellness-text-muted: #6b7280;
}
```

#### Using Brand Kits in Your Design System

Once you have your brand kit defined, map it to your design system:

```css
:root {
  /* Map brand colors to design system */
  --color-primary-500: var(--brand-primary);
  --color-primary-600: var(--brand-primary-dark);
  --color-primary-400: var(--brand-primary-light);
  
  --color-secondary-500: var(--brand-secondary);
  --color-accent-500: var(--brand-accent);
  
  /* Use brand colors in components */
  --btn-primary-bg: var(--brand-primary);
  --btn-primary-hover: var(--brand-primary-dark);
  --link-color: var(--brand-primary);
  --focus-ring: var(--brand-primary-light);
}
```

#### Brand Kit Best Practices

1. **Color Accessibility**: Ensure brand colors meet WCAG contrast requirements
   - Use tools like **WebAIM Contrast Checker**
   - Minimum 4.5:1 for normal text, 3:1 for large text

2. **Create Tints and Shades**: Generate lighter/darker variants
   - Lighten: Mix with white (10%, 20%, 30%, etc.)
   - Darken: Mix with black or saturate
   - Use tools like **0to255.com** or **Paletton.com**

3. **Document Your Brand Kit**: Create a style guide
   ```markdown
   # Brand Colors
   
   ## Primary Color: Energetic Orange
   - Hex: #ff6b35
   - RGB: rgb(255, 107, 53)
   - Use: Primary buttons, links, CTAs
   
   ## Secondary Color: Professional Navy
   - Hex: #1a2238
   - RGB: rgb(26, 34, 56)
   - Use: Headers, navigation, footer
   ```

4. **Test Combinations**: Ensure colors work well together
   - Primary + Secondary
   - Primary + Neutral
   - Accent + Background

5. **Consider Context**: Different colors for different purposes
   - **CTAs**: Use primary brand color
   - **Success states**: Green (or brand-appropriate alternative)
   - **Warnings**: Amber/Orange
   - **Errors**: Red (or brand-appropriate alternative)

#### Quick Brand Kit Generator Template

```css
/* Copy this template and fill in your brand colors */
:root {
  /* === YOUR BRAND COLORS === */
  --brand-primary: #REPLACE_ME;        /* Main brand color */
  --brand-secondary: #REPLACE_ME;      /* Supporting color */
  --brand-accent: #REPLACE_ME;         /* Highlight color */
  
  /* === AUTO-GENERATED VARIANTS === */
  /* Lighten primary by ~20% */
  --brand-primary-light: #REPLACE_ME;
  /* Darken primary by ~20% */
  --brand-primary-dark: #REPLACE_ME;
  
  /* === NEUTRALS === */
  --brand-bg: #f8f9fa;
  --brand-card: #ffffff;
  --brand-text: #1a1a1a;
  --brand-text-muted: #6c757d;
  
  /* === SEMANTIC (adjust to match brand) === */
  --brand-success: #10b981;
  --brand-warning: #f59e0b;
  --brand-error: #ef4444;
  --brand-info: var(--brand-primary);
  
  /* === GRADIENTS === */
  --brand-gradient: linear-gradient(135deg, var(--brand-primary) 0%, var(--brand-secondary) 100%);
}
```

---

### 4. **Typography Excellence**
Always use modern, professional fonts:

```html
<!-- Import Google Fonts -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@300;400;500;600;700;800&family=Poppins:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
```

```css
/* Typography System */
:root {
  --font-primary: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-display: 'Outfit', sans-serif;
  --font-accent: 'Poppins', sans-serif;
  
  /* Type Scale */
  --text-xs: 0.75rem;    /* 12px */
  --text-sm: 0.875rem;   /* 14px */
  --text-base: 1rem;     /* 16px */
  --text-lg: 1.125rem;   /* 18px */
  --text-xl: 1.25rem;    /* 20px */
  --text-2xl: 1.5rem;    /* 24px */
  --text-3xl: 1.875rem;  /* 30px */
  --text-4xl: 2.25rem;   /* 36px */
  --text-5xl: 3rem;      /* 48px */
  
  /* Line Heights */
  --leading-tight: 1.25;
  --leading-normal: 1.5;
  --leading-relaxed: 1.75;
}

body {
  font-family: var(--font-primary);
  font-size: var(--text-base);
  line-height: var(--leading-normal);
}

h1, h2, h3 {
  font-family: var(--font-display);
  font-weight: 700;
  line-height: var(--leading-tight);
}
```

---

## 🌟 Modern Design Patterns

### Glassmorphism
```css
.glass-card {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 16px;
  box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.15);
}

/* Dark mode variant */
.glass-card-dark {
  background: rgba(26, 26, 46, 0.7);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
}
```

### Neumorphism (Soft UI)
```css
.neomorphic {
  background: #e0e5ec;
  border-radius: 20px;
  box-shadow: 
    9px 9px 16px rgba(163, 177, 198, 0.6),
    -9px -9px 16px rgba(255, 255, 255, 0.5);
}

.neomorphic-inset {
  background: #e0e5ec;
  border-radius: 20px;
  box-shadow: 
    inset 9px 9px 16px rgba(163, 177, 198, 0.6),
    inset -9px -9px 16px rgba(255, 255, 255, 0.5);
}
```

### Gradient Borders
```css
.gradient-border {
  position: relative;
  background: #1a1a2e;
  border-radius: 16px;
  padding: 2px;
}

.gradient-border::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 16px;
  padding: 2px;
  background: linear-gradient(135deg, #667eea, #764ba2);
  -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
}

.gradient-border-content {
  position: relative;
  background: #1a1a2e;
  border-radius: 14px;
  padding: 1.5rem;
}
```

---

## ✨ Micro-Animations

### Hover Effects
```css
/* Smooth lift on hover */
.lift-on-hover {
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1),
              box-shadow 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.lift-on-hover:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.15);
}

/* Glow effect */
.glow-on-hover {
  transition: box-shadow 0.3s ease;
}

.glow-on-hover:hover {
  box-shadow: 0 0 20px rgba(102, 126, 234, 0.6),
              0 0 40px rgba(102, 126, 234, 0.4);
}

/* Scale and rotate */
.scale-rotate {
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.scale-rotate:hover {
  transform: scale(1.05) rotate(2deg);
}

/* Gradient shift */
.gradient-shift {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  background-size: 200% 200%;
  transition: background-position 0.5s ease;
}

.gradient-shift:hover {
  background-position: 100% 0;
}
```

### Loading Animations
```css
/* Skeleton loader */
@keyframes shimmer {
  0% { background-position: -1000px 0; }
  100% { background-position: 1000px 0; }
}

.skeleton {
  background: linear-gradient(
    90deg,
    #f0f0f0 0px,
    #e0e0e0 40px,
    #f0f0f0 80px
  );
  background-size: 1000px 100%;
  animation: shimmer 2s infinite;
}

/* Pulse animation */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.pulse {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

/* Spin animation */
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.spin {
  animation: spin 1s linear infinite;
}
```

### Page Transitions
```css
/* Fade in from bottom */
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.fade-in-up {
  animation: fadeInUp 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Stagger children */
.stagger-children > * {
  animation: fadeInUp 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

.stagger-children > *:nth-child(1) { animation-delay: 0.1s; }
.stagger-children > *:nth-child(2) { animation-delay: 0.2s; }
.stagger-children > *:nth-child(3) { animation-delay: 0.3s; }
.stagger-children > *:nth-child(4) { animation-delay: 0.4s; }
```

---

## 🎯 Premium Component Patterns

### Modern Button System
```css
/* Primary Button */
.btn-primary {
  font-family: var(--font-primary);
  font-weight: 600;
  font-size: var(--text-base);
  padding: 0.75rem 1.5rem;
  border-radius: 12px;
  border: none;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(102, 126, 234, 0.4);
}

.btn-primary:active {
  transform: translateY(0);
}

/* Ghost Button */
.btn-ghost {
  font-family: var(--font-primary);
  font-weight: 600;
  padding: 0.75rem 1.5rem;
  border-radius: 12px;
  border: 2px solid #667eea;
  background: transparent;
  color: #667eea;
  cursor: pointer;
  transition: all 0.3s ease;
}

.btn-ghost:hover {
  background: #667eea;
  color: white;
}

/* Icon Button */
.btn-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  border: none;
  background: rgba(102, 126, 234, 0.1);
  color: #667eea;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s ease;
}

.btn-icon:hover {
  background: #667eea;
  color: white;
  transform: scale(1.1);
}
```

### Card Components
```css
/* Modern Card */
.card-modern {
  background: white;
  border-radius: 20px;
  padding: 2rem;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid rgba(0, 0, 0, 0.05);
}

.card-modern:hover {
  transform: translateY(-8px);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.12);
}

/* Feature Card with Icon */
.feature-card {
  background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
  border-radius: 24px;
  padding: 2.5rem;
  text-align: center;
  transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.feature-card:hover {
  transform: scale(1.05);
  background: linear-gradient(135deg, #667eea25 0%, #764ba225 100%);
}

.feature-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 1.5rem;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 2rem;
}
```

### Input Fields
```css
/* Modern Input */
.input-modern {
  width: 100%;
  padding: 1rem 1.25rem;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  font-family: var(--font-primary);
  font-size: var(--text-base);
  transition: all 0.3s ease;
  background: white;
}

.input-modern:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 4px rgba(102, 126, 234, 0.1);
}

.input-modern::placeholder {
  color: #94a3b8;
}

/* Floating Label Input */
.input-group {
  position: relative;
  margin-top: 1.5rem;
}

.input-floating {
  width: 100%;
  padding: 1rem 1.25rem;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  font-family: var(--font-primary);
  font-size: var(--text-base);
  transition: all 0.3s ease;
}

.input-label {
  position: absolute;
  left: 1.25rem;
  top: 1rem;
  color: #94a3b8;
  font-size: var(--text-base);
  transition: all 0.3s ease;
  pointer-events: none;
  background: white;
  padding: 0 0.25rem;
}

.input-floating:focus + .input-label,
.input-floating:not(:placeholder-shown) + .input-label {
  top: -0.5rem;
  font-size: var(--text-sm);
  color: #667eea;
}
```

---

## 📐 Layout Systems

### Responsive Grid
```css
/* Modern Grid System */
.grid-auto {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 2rem;
}

.grid-2 {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 2rem;
}

.grid-3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 2rem;
}

.grid-4 {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 2rem;
}

/* Responsive breakpoints */
@media (max-width: 1024px) {
  .grid-4 { grid-template-columns: repeat(2, 1fr); }
  .grid-3 { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 640px) {
  .grid-4,
  .grid-3,
  .grid-2 {
    grid-template-columns: 1fr;
  }
}
```

### Flexbox Utilities
```css
.flex { display: flex; }
.flex-col { flex-direction: column; }
.flex-wrap { flex-wrap: wrap; }

.items-center { align-items: center; }
.items-start { align-items: flex-start; }
.items-end { align-items: flex-end; }

.justify-center { justify-content: center; }
.justify-between { justify-content: space-between; }
.justify-around { justify-content: space-around; }

.gap-1 { gap: 0.25rem; }
.gap-2 { gap: 0.5rem; }
.gap-3 { gap: 0.75rem; }
.gap-4 { gap: 1rem; }
.gap-6 { gap: 1.5rem; }
.gap-8 { gap: 2rem; }
```

---

## 🎨 Complete Design System Template

```css
/* ========================================
   DESIGN SYSTEM - [Your Project Name]
   ======================================== */

:root {
  /* === COLORS === */
  /* Primary Palette */
  --color-primary-50: #f5f7ff;
  --color-primary-100: #ebf0ff;
  --color-primary-200: #d6e0ff;
  --color-primary-300: #b3c7ff;
  --color-primary-400: #809fff;
  --color-primary-500: #667eea;
  --color-primary-600: #5568d3;
  --color-primary-700: #4453b8;
  --color-primary-800: #3a4694;
  --color-primary-900: #2d3670;
  
  /* Accent Palette */
  --color-accent-500: #764ba2;
  --color-accent-600: #5f3c82;
  
  /* Neutral Palette */
  --color-gray-50: #f8fafc;
  --color-gray-100: #f1f5f9;
  --color-gray-200: #e2e8f0;
  --color-gray-300: #cbd5e1;
  --color-gray-400: #94a3b8;
  --color-gray-500: #64748b;
  --color-gray-600: #475569;
  --color-gray-700: #334155;
  --color-gray-800: #1e293b;
  --color-gray-900: #0f172a;
  
  /* Semantic Colors */
  --color-success: #10b981;
  --color-warning: #f59e0b;
  --color-error: #ef4444;
  --color-info: #3b82f6;
  
  /* === TYPOGRAPHY === */
  --font-primary: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-display: 'Outfit', sans-serif;
  
  /* Font Sizes */
  --text-xs: 0.75rem;
  --text-sm: 0.875rem;
  --text-base: 1rem;
  --text-lg: 1.125rem;
  --text-xl: 1.25rem;
  --text-2xl: 1.5rem;
  --text-3xl: 1.875rem;
  --text-4xl: 2.25rem;
  --text-5xl: 3rem;
  
  /* Font Weights */
  --font-light: 300;
  --font-normal: 400;
  --font-medium: 500;
  --font-semibold: 600;
  --font-bold: 700;
  --font-extrabold: 800;
  
  /* === SPACING === */
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-5: 1.25rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --space-10: 2.5rem;
  --space-12: 3rem;
  --space-16: 4rem;
  --space-20: 5rem;
  
  /* === BORDERS === */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 20px;
  --radius-2xl: 24px;
  --radius-full: 9999px;
  
  /* === SHADOWS === */
  --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
  --shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
  --shadow-2xl: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
  
  /* === TRANSITIONS === */
  --transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-base: 300ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-slow: 500ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-bounce: 400ms cubic-bezier(0.34, 1.56, 0.64, 1);
}

/* === BASE STYLES === */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: var(--font-primary);
  font-size: var(--text-base);
  line-height: 1.6;
  color: var(--color-gray-900);
  background: var(--color-gray-50);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

h1, h2, h3, h4, h5, h6 {
  font-family: var(--font-display);
  font-weight: var(--font-bold);
  line-height: 1.25;
  color: var(--color-gray-900);
}

h1 { font-size: var(--text-5xl); }
h2 { font-size: var(--text-4xl); }
h3 { font-size: var(--text-3xl); }
h4 { font-size: var(--text-2xl); }
h5 { font-size: var(--text-xl); }
h6 { font-size: var(--text-lg); }

a {
  color: var(--color-primary-500);
  text-decoration: none;
  transition: color var(--transition-fast);
}

a:hover {
  color: var(--color-primary-600);
}
```

---

## 🚀 Implementation Checklist

When creating a new page or component, follow this checklist:

- [ ] **Import modern fonts** (Inter, Outfit, or Poppins)
- [ ] **Define color palette** (no basic colors!)
- [ ] **Set up CSS variables** for consistency
- [ ] **Create responsive grid/flex layouts**
- [ ] **Add hover effects** to interactive elements
- [ ] **Implement micro-animations** (fade-in, lift, glow)
- [ ] **Use proper spacing** (generous whitespace)
- [ ] **Add shadows** for depth
- [ ] **Ensure mobile responsiveness**
- [ ] **Test dark mode** (if applicable)
- [ ] **Optimize performance** (minimize animations on mobile)

---

## 💡 Quick Tips

1. **Never use default browser styles** - always customize
2. **Gradients > Solid colors** - they add depth and interest
3. **Animations should be subtle** - 300-400ms is ideal
4. **Mobile-first approach** - design for small screens first
5. **Accessibility matters** - ensure sufficient color contrast
6. **Consistency is key** - use your design system variables
7. **Test on real devices** - not just browser dev tools
8. **Performance first** - beautiful but slow = bad UX

---

## 📚 Resources

### Inspiration Sites
- **Dribbble** - UI design inspiration
- **Awwwards** - Award-winning web design
- **Behance** - Creative portfolios
- **Mobbin** - Mobile app design patterns

### Color Tools
- **Coolors.co** - Color palette generator
- **ColorHunt** - Curated color palettes
- **Adobe Color** - Color wheel, harmony rules, and image color extraction
- **Paletton.com** - Advanced color scheme designer
- **0to255.com** - Find lighter and darker colors
- **ImageColorPicker.com** - Extract colors from images
- **WebAIM Contrast Checker** - Ensure accessibility compliance

### Brand Kit Tools
- **Brandfetch** - Download brand assets and colors from any website
- **Brand.ai** - Manage and share brand design systems
- **Frontify** - Complete brand management platform
- **Figma** - Design tool with brand kit features

### Typography
- **Google Fonts** - Free web fonts
- **FontPair** - Font pairing suggestions
- **Type Scale** - Typography scale calculator
- **Fontjoy** - AI-powered font pairing

---

## 🎯 Example: Complete Modern Page Template

See `examples/modern-page-template.html` for a complete, production-ready example implementing all these principles.

---

**Remember**: The goal is to create interfaces that feel premium, modern, and alive. Every element should have purpose, polish, and personality!
