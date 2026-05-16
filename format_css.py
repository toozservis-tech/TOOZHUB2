import re

with open("web/service-shell.css", "r", encoding="utf-8") as f:
    css = f.read()

# 1. Update font sizes and paddings to be more compact
css = re.sub(r'font-size: 3rem;', 'font-size: 2.2rem;', css)
css = re.sub(r'font-size: 2.2rem;', 'font-size: 1.8rem;', css)
css = re.sub(r'font-size: 1.5rem;', 'font-size: 1.25rem;', css)
css = re.sub(r'font-size: 0.98rem;', 'font-size: 0.9rem;', css)

# 2. Update border radiuses to use CSS variables where they are hardcoded
css = re.sub(r'border-radius: 14px;', 'border-radius: var(--service-radius-sm);', css)
css = re.sub(r'border-radius: 16px;', 'border-radius: var(--service-radius-sm);', css)
css = re.sub(r'border-radius: 18px;', 'border-radius: var(--service-radius);', css)
css = re.sub(r'border-radius: 22px;', 'border-radius: var(--service-radius);', css)
css = re.sub(r'border-radius: 24px;', 'border-radius: var(--service-radius);', css)

# 3. Update min-heights for inputs and buttons (Desktop sizes)
css = re.sub(r'min-height: 46px;', 'min-height: 36px;', css)
css = re.sub(r'min-height: 48px;', 'min-height: 38px;', css)
css = re.sub(r'min-height: 44px;', 'min-height: 36px;', css)
css = re.sub(r'min-height: 50px;', 'min-height: 38px;', css)
css = re.sub(r'width: 46px;\s*height: 46px;', 'width: 36px;\n  height: 36px;', css)
css = re.sub(r'width: 48px;\s*height: 48px;', 'width: 38px;\n  height: 38px;', css)

# 4. Clean up primary button and icon button (remove heavy gradients/shadows)
css = re.sub(r'background: linear-gradient\(135deg, var\(--service-primary\) 0%, var\(--service-primary-strong\) 100%\);', 'background: var(--service-primary);', css)
css = re.sub(r'box-shadow: 0 14px 28px rgba\(37, 99, 235, 0\.18\);', 'box-shadow: 0 2px 8px rgba(37, 99, 235, 0.2);', css)

# 5. Modals and padding
css = re.sub(r'padding: 22px 28px;', 'padding: 16px 20px;', css)
css = re.sub(r'padding: 24px;', 'padding: 20px;', css)
css = re.sub(r'padding: 24px 28px 34px;', 'padding: 20px 24px;', css)
css = re.sub(r'padding: 12px 18px;', 'padding: 8px 14px;', css)
css = re.sub(r'padding: 16px 12px;', 'padding: 10px 12px;', css)
css = re.sub(r'padding: 14px 16px;', 'padding: 12px 14px;', css)

with open("web/service-shell.css", "w", encoding="utf-8") as f:
    f.write(css)

