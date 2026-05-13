from typing import List, Dict, Any
from datetime import datetime
import re
import json
from app.core.config import settings


class ReportService:
    """Service for generating data analysis reports."""
    
    def __init__(self):
        pass
    
    def generate_report_prompt(
        self,
        conversation_title: str,
        user_query: str,
        messages: List[Dict[str, Any]],
        tool_calls: List[Dict[str, Any]],
        generated_files: List[Dict[str, Any]] | None = None
    ) -> str:
        """Generate a prompt for LLM to create a comprehensive report."""
        
        # Extract execution summary
        execution_summary = []
        for idx, tc in enumerate(tool_calls):
            tool_name = tc.get("name", "unknown")
            tool_args = tc.get("arguments", "{}")
            result = tc.get("result", {})
            
            try:
                args = json.loads(tool_args) if isinstance(tool_args, str) else tool_args
                code = args.get("code", "")[:500]  # Limit code length
            except:
                code = str(tool_args)[:500]
            
            stdout = result.get("stdout", "")[:1000] if result else ""
            stderr = result.get("stderr", "")[:500] if result else ""
            images = result.get("images", []) if result else []
            
            execution_summary.append(f"""
Step {idx + 1}: {tool_name}
Code:
```python
{code}
```
Output:
{stdout}
{('Errors: ' + stderr) if stderr else ''}
{('Images generated: ' + ', '.join(images)) if images else ''}
""")
        
        execution_text = "\n".join(execution_summary) if execution_summary else "No code execution."

        generated_assets_text = self._build_generated_assets_section(generated_files or [])
        
        # Extract LLM responses
        llm_responses = []
        for msg in messages:
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                # Split off execution details if present
                parts = content.split("---")
                main_response = parts[0].strip() if parts else content
                if main_response:
                    llm_responses.append(main_response)
        
        llm_text = "\n\n".join(llm_responses) if llm_responses else "No analysis provided."
        
        prompt = f"""You are a professional data scientist writing a comprehensive analysis report. 

TASK: Based on the following conversation and code execution history, generate a well-structured data analysis report in Markdown format.

USER'S ORIGINAL QUESTION:
{user_query}

CONVERSATION CONTEXT:
Title: {conversation_title}

LLM'S ANALYSIS AND INSIGHTS:
{llm_text}

CODE EXECUTION HISTORY:
{execution_text}

GENERATED VISUAL ASSETS:
{generated_assets_text}

REPORT REQUIREMENTS:
1. **Executive Summary**: Brief overview of the analysis and key findings
2. **Introduction**: Context and objectives of the analysis
3. **Methodology**: Description of the approach and tools used
4. **Data Analysis**: Detailed findings with references to code execution
5. **Results**: Key outcomes, statistics, and visualizations (reference the images generated)
6. **Conclusions**: Summary of insights and recommendations
7. **Technical Appendix**: Summary of code executed (optional)

FORMATTING GUIDELINES:
- Use proper Markdown formatting with headers (# ## ###)
- Include tables where appropriate for data presentation
- Reference any generated figures/images in the Results section
- When a relevant generated asset exists, reference it inline exactly by its filename alias, for example `[correlation_heatmap.png]`, and place the corresponding markdown image directly below that discussion
- Use centered 80% width HTML image blocks for generated figures, for example:
  `<p align="center"><img src="IMAGE_URL" alt="correlation heatmap" width="80%"></p>`
- Do not group unrelated images into a single generic subsection if the filenames indicate different purposes
- Use professional, clear language suitable for both technical and non-technical audiences
- Include specific numbers and statistics from the execution output
- Format code blocks with proper syntax highlighting

Generate a complete, professional report below:

---

# Data Analysis Report: {conversation_title}

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Analysis Type:** {self._infer_analysis_type(user_query)}

## Executive Summary

[Provide 2-3 paragraphs summarizing the entire analysis, key findings, and recommendations]

## Introduction

### Objective
{user_query}

### Background
[Context about the data and analysis goals]

## Methodology

### Tools and Libraries Used
[List Python libraries used: pandas, matplotlib, numpy, etc.]

### Approach
[Describe the analytical approach taken]

## Data Analysis

### Code Implementation
[Reference key code snippets and explain their purpose]

### Execution Results
[Summarize what was executed and what was learned]

## Results and Findings

### Key Statistics
[Extract and present key numbers from the output]

### Visualizations
[Describe any charts/images generated and their significance]

## Conclusions

### Summary of Insights
[Bullet points of main findings]

### Recommendations
[Actionable recommendations based on the analysis]

### Limitations
[Any limitations or caveats about the analysis]

## Technical Appendix

### Complete Code Executed
[Optional: Full code listing]

---

**Report End**
"""
        
        return prompt
    
    def _infer_analysis_type(self, query: str) -> str:
        """Infer the type of analysis from the query."""
        query_lower = query.lower()
        
        if any(word in query_lower for word in ["visualization", "plot", "chart", "graph", "draw", "image"]):
            return "Data Visualization"
        elif any(word in query_lower for word in ["statistic", "correlation", "regression", "analysis", "model"]):
            return "Statistical Analysis"
        elif any(word in query_lower for word in ["clean", "preprocess", "transform", "prepare"]):
            return "Data Preprocessing"
        elif any(word in query_lower for word in ["sql", "database", "query"]):
            return "Database Analysis"
        elif any(word in query_lower for word in ["machine learning", "ml", "train", "predict", "classify"]):
            return "Machine Learning"
        else:
            return "General Data Analysis"
    
    def create_report_markdown(
        self,
        conversation_title: str,
        messages: List[Dict[str, Any]],
        tool_calls: List[Dict[str, Any]],
        generated_report: str = None,
        generated_files: List[Dict[str, Any]] | None = None
    ) -> str:
        """Create a markdown report from conversation history."""
        
        if generated_report:
            # Use LLM-generated report
            return generated_report
        
        # Fallback: Create a basic report structure
        report = f"""# Data Analysis Report: {conversation_title}

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Conversation Summary

"""
        
        # Add messages
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            
            if role == "user":
                report += f"### User Query\n\n{content}\n\n"
            elif role == "assistant":
                # Split main content from execution details
                parts = content.split("---")
                main_content = parts[0].strip() if parts else content
                report += f"### Analysis\n\n{main_content}\n\n"
        
        # Add execution details
        if tool_calls:
            report += "## Code Execution\n\n"
            for idx, tc in enumerate(tool_calls):
                report += f"### Step {idx + 1}: {tc.get('name', 'Unknown')}\n\n"
                
                try:
                    args = json.loads(tc.get("arguments", "{}"))
                    code = args.get("code", "")
                    if code:
                        report += f"```python\n{code}\n```\n\n"
                except:
                    pass
                
                result = tc.get("result", {})
                if result:
                    if result.get("stdout"):
                        report += f"**Output:**\n```\n{result['stdout']}\n```\n\n"
                    if result.get("images"):
                        report += f"**Generated Images:**\n"
                        for img in result["images"]:
                            report += f"![Generated Image]({img})\n"
                        report += "\n"

        if generated_files:
            report += "## Generated Assets\n\n"
            for item in generated_files:
                report += f"- [{item['name']}] {item['description']}\n"
                report += f"  ![{item['description']}]({item['url']})\n\n"
        
        return report

    def _build_generated_assets_section(self, generated_files: List[Dict[str, Any]]) -> str:
        if not generated_files:
            return "No generated assets available."

        lines = []
        for item in generated_files:
            lines.append(
                f"- [{item['name']}] {item['description']}\n"
                f"  Markdown: ![{item['description']}]({item['url']})"
            )
        return "\n".join(lines)
