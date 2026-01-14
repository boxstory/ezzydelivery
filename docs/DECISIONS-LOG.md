# Decisions Log

## Why We Did What We Did

---

## 2026-01-13 - Business Team Permission System

**Problem:** Needed granular permission control for business team members
**Options Considered:**
1. Django's built-in permission system
2. Custom permission model with team-level access
3. Third-party package (django-guardian)

**Decision:** Custom permission model integrated with business teams
**Why:** Better fits multi-tenant architecture; team-level permissions are more intuitive for business users than Django's per-object permissions

---

## 2026-01-13 - QR Code Instead of Barcode

**Problem:** Original barcode system hard to scan reliably on mobile devices
**Options Considered:**
1. Keep barcodes, improve scanner
2. Switch to QR codes
3. Support both

**Decision:** Replace barcodes with QR codes
**Why:** QR codes more reliable for mobile scanning, contain more data, work with standard phone cameras

---

## 2025-11-27 - Social Authentication Provider Choice

**Problem:** Users requested social login options
**Options Considered:**
1. Google only
2. Google + Facebook
3. Google + Facebook + Twitter + GitHub

**Decision:** Google + Facebook only
**Why:** These are the most common providers in Qatar market; Twitter/GitHub less relevant for delivery platform users

---

## 2025-11-27 - CSS Brand Kit System

**Problem:** Inconsistent colors and styles across templates
**Options Considered:**
1. Material Kit (existing)
2. Custom Brand Kit with CSS variables
3. Tailwind CSS migration

**Decision:** Custom Brand Kit with CSS variables
**Why:**
- Less overhead than Tailwind migration
- Full control over design system
- CSS variables allow easy theming
- Removes Material Kit dependency

---

## 2025-11-22 - Inline Styles Extraction Strategy

**Problem:** 100+ templates with inline styles violating code conventions
**Options Considered:**
1. Fix all at once (risky)
2. Fix on-touch (slow)
3. Batch extraction with QA tracking

**Decision:** Batch extraction with qa_todos.md tracking
**Why:** Systematic approach allows progress tracking; lower risk than big-bang refactor; enables parallel work by multiple agents

---

## Template Decision - kebab-case CSS Classes

**Problem:** Mixed class naming conventions (snake_case, camelCase, kebab-case)
**Options Considered:**
1. Standardize on snake_case (Python convention)
2. Standardize on kebab-case (CSS convention)
3. Allow mixed

**Decision:** Standardize on kebab-case for CSS classes
**Why:** Industry standard for CSS; matches Bootstrap/most frameworks; IDs can remain snake_case for Django template compatibility

---

## Query Optimization Standard

**Problem:** N+1 query issues in list views
**Decision:** Mandatory use of `select_related()` for FK and `prefetch_related()` for reverse relations
**Why:** Prevents performance degradation as data grows; established Django best practice

---

## Authentication Decorator Policy

**Problem:** Inconsistent authentication on views
**Decision:** All views must use `@login_required` or `@business_permission_required`
**Why:** Security first; no unauthenticated access to business data
