# CSS px to rem Conversion Rule

## Rule
**All CSS pixel values must be converted to rem units** for better accessibility and responsive scaling.

## Conversion Formula
```
rem = px / 16
```

Base font size is 16px, so:
- 1px = 0.0625rem
- 2px = 0.125rem
- 4px = 0.25rem
- 8px = 0.5rem
- 10px = 0.625rem
- 12px = 0.75rem
- 14px = 0.875rem
- 16px = 1rem
- 18px = 1.125rem
- 20px = 1.25rem
- 24px = 1.5rem
- 28px = 1.75rem
- 32px = 2rem
- 36px = 2.25rem
- 40px = 2.5rem
- 44px = 2.75rem
- 48px = 3rem
- 56px = 3.5rem
- 64px = 4rem
- 80px = 5rem
- 96px = 6rem
- 100px = 6.25rem
- 120px = 7.5rem
- 140px = 8.75rem
- 200px = 12.5rem

## Exceptions (Keep as px)
- `1px` borders (hairline borders)
- Media query breakpoints (e.g., `@media (max-width: 768px)`)
- Box shadows (small px values for precise control)
- `border-width` when 1-2px

## Examples

### Before (px)
```css
.button {
  padding: 12px 24px;
  font-size: 16px;
  border-radius: 8px;
  margin-bottom: 16px;
}
```

### After (rem)
```css
.button {
  padding: 0.75rem 1.5rem;
  font-size: 1rem;
  border-radius: 0.5rem;
  margin-bottom: 1rem;
}
```

## Why rem?
1. **Accessibility**: Users can adjust browser font size, and rem scales with it
2. **Consistency**: All sizes relative to root font size
3. **Responsive**: Easier to scale entire design by changing root font size
4. **Best Practice**: Modern CSS standard for sizing
