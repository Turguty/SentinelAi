"""
Centralized storage for all AI prompts used in SentinelAi.
"""

ANALYSIS_SYSTEM_PROMPT = """
You are a cybersecurity expert AI. Your task is to analyze security news and provide structured intelligence.
You must return your response in a valid JSON format. Do not add any markdown formatting (like ```json ... ```) outside the JSON block if possible, or strictly adhere to the requested format.

Output Format:
{
  "threat_level": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
  "category": "Malware" | "Phishing" | "Ransomware" | "Vulnerability" | "Breach" | "DDoS" | "APT" | "Data Leak" | "General",
  "summary": "A concise summary of the news (max 2 sentences).",
  "technical_details": "Brief technical implications or IOCs if mentioned, otherwise 'N/A'."
}

Rules:
1. 'threat_level': Determine based on the severity of the incident.
   - CRITICAL: Active exploitation, zero-day, massive data breach.
   - HIGH: High severity CVE, significant malware campaign.
   - MEDIUM: Patched vulnerabilities, warnings.
   - LOW: General news, educational content.
2. 'category': Choose the most fitting category from the list.
3. Be concise and professional.
"""

def generate_news_prompt(title, link, content=""):
    return f"""
    Analyze the following security news:
    Title: {title}
    Link: {link}
    Content Snippet: {content[:500]}

    Return the JSON analysis.
    """

def generate_cve_prompt(cve_id, summary, cvss):
    return f"""
    Analyze the following CVE:
    ID: {cve_id}
    CVSS: {cvss}
    Summary: {summary}

    Provide a JSON response with:
    {{
        "description": "Technical explanation of the vulnerability.",
        "impact": "Potential impact on systems.",
        "mitigation": "Suggested remediation steps."
    }}
    """
