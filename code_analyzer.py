"""
Advanced Code Analysis and Optimization Tool for ReVibe System
Using OpenAI GPT-4o for comprehensive code review and fixes
"""

import os
import json
from openai import OpenAI

# the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
# do not change this unless explicitly requested by the user
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

def analyze_code_file(file_path, file_content):
    """
    Use GPT-4o to analyze code file for issues and optimizations
    """
    try:
        prompt = f"""
        You are an expert Python/Flask developer and code auditor. Analyze this file from a production ReVibe inventory management system.

        File: {file_path}
        Content:
        ```python
        {file_content}
        ```

        Perform a comprehensive analysis and identify:
        1. Type safety issues and null pointer exceptions
        2. Database transaction safety and rollback handling
        3. Security vulnerabilities (SQL injection, XSS, CSRF)
        4. Performance optimizations and efficiency improvements
        5. Error handling and exception management
        6. Code quality and best practices
        7. Memory leaks or resource management issues
        8. Potential race conditions or concurrency issues

        Return your analysis in JSON format with specific fixes:
        {{
            "critical_issues": [
                {{
                    "line": number,
                    "issue": "description",
                    "severity": "critical|high|medium|low",
                    "fix": "exact code fix"
                }}
            ],
            "optimizations": [
                {{
                    "area": "performance|security|maintainability",
                    "improvement": "description",
                    "code_change": "exact code change"
                }}
            ],
            "overall_rating": "excellent|good|needs_improvement|critical",
            "summary": "brief summary of code quality"
        }}
        """

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        return json.loads(response.choices[0].message.content)
    
    except Exception as e:
        print(f"Error analyzing {file_path}: {e}")
        return {"error": str(e)}

def get_comprehensive_system_analysis():
    """
    Analyze all critical system files
    """
    critical_files = [
        'routes.py',
        'models.py', 
        'forms.py',
        'utils.py',
        'ai_product_identifier.py',
        'receipt_generator.py',
        'pdf_generator.py',
        'barcode_scanner.py'
    ]
    
    analysis_results = {}
    
    for file_path in critical_files:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
            analysis_results[file_path] = analyze_code_file(file_path, content)
    
    return analysis_results

if __name__ == "__main__":
    results = get_comprehensive_system_analysis()
    print(json.dumps(results, indent=2))