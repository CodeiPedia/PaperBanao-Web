# === NEW FEATURE: HTML A4 GENERATOR WITH MATH SUPPORT ===
def create_a4_html(md_content):
    # Convert AI Markdown to HTML
    html_body = markdown.markdown(md_content)
    
    # CSS Magic and MathJax for A4 Print
    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Question Paper</title>
        
        <script>
          MathJax = {{
            tex: {{
              inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
              displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']]
            }}
          }};
        </script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>

        <style>
            body {{
                background-color: #f0f0f0;
                font-family: 'Times New Roman', Times, serif;
                margin: 0;
                padding: 20px;
                display: flex;
                justify-content: center;
            }}
            .a4-page {{
                background-color: white;
                width: 210mm;
                min-height: 297mm;
                padding: 20mm;
                box-sizing: border-box;
                box-shadow: 0 0 10px rgba(0,0,0,0.2);
            }}
            @media print {{
                body {{ background-color: white; padding: 0; display: block; }}
                .a4-page {{ box-shadow: none; width: 100%; padding: 0; margin: 0; }}
                @page {{ size: A4; margin: 20mm; }}
            }}
            h1, h2, h3 {{ text-align: center; color: #111; }}
            p, li {{ font-size: 16px; line-height: 1.5; color: #000; }}
            hr {{ border: 1px solid #ccc; margin: 20px 0; }}
            
            /* Make sure math formulas wrap nicely */
            mjx-container {{
                max-width: 100%;
                overflow-x: auto;
                overflow-y: hidden;
            }}
        </style>
    </head>
    <body>
        <div class="a4-page">
            {html_body}
        </div>
    </body>
    </html>
    """
    return html_template
