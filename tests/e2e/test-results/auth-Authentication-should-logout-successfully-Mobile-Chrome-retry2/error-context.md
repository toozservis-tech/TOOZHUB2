# Page snapshot

```yaml
- generic [ref=e5]:
  - heading "Přihlášení" [level=2] [ref=e6]
  - generic [ref=e7]:
    - generic [ref=e8]: "Email:"
    - textbox "Email:" [ref=e9]:
      - /placeholder: email@example.com
      - text: toozservis@gmail.com
  - generic [ref=e10]:
    - generic [ref=e11]: "Heslo:"
    - textbox "Heslo:" [ref=e12]:
      - /placeholder: Heslo
      - text: "123456"
  - generic [ref=e13]:
    - button "Přihlásit se" [active] [ref=e14] [cursor=pointer]
    - button "Registrace" [ref=e15] [cursor=pointer]
  - link "Zapomenuté heslo?" [ref=e17] [cursor=pointer]:
    - /url: "#"
  - generic [ref=e20]: Nepodařilo se připojit k serveru. Zkontrolujte, zda server běží a API URL je správně nastavena.
```