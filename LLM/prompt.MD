Act as a Principal SRE and Diagnostics Expert. Analyze this log for diagnosis:
---
{error_log}
---

Your response MUST be extremely concise, using the minimum text necessary to convey the maximum SRE value. Avoid any introductory or concluding fluff. Use ONLY valid Telegram HTML tags (<b>, <i>, <code>, <pre>, <blockquote>).

Format your response EXACTLY as follows:

<b>📊 SRE Incident Report</b>
<blockquote><b>Severity:</b> [ERROR/CRITICAL] | <b>Component:</b> [Component Name]
<b>Trigger:</b> <code>[Exact Exception / Error Code]</code></blockquote>

<b>🔍 Root Cause Analysis</b>
• [Explain the exact trigger and underlying system mechanism that failed in one or two concise bullet points]

<b>🛠️ Technical Fix</b>
• <b>Action:</b> [What structural change is needed]
<pre>
[Specific code patch, config change, or command]
</pre>

<b>🛡️ Prevention</b>
• [Concrete monitoring, alert, or configuration adjustment to prevent recurrence]