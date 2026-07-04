import re
from mcp.server.fastmcp import FastMCP

# Create an MCP server named "edupath-mcp-server"
mcp = FastMCP("edupath-mcp-server")

@mcp.tool()
def search_educational_resources(query: str) -> str:
    """Search for free educational resources (textbooks, videos, articles) for a given topic.
    
    Args:
        query: The educational topic to search for.
        
    Returns:
        A formatted string containing a list of free learning resources with URLs.
    """
    # Simple structured mock database for common subjects
    resources = {
        "python": [
            {"title": "Python for Everybody", "url": "https://www.py4e.com/", "desc": "Free textbook, video lectures, and auto-graded exercises."},
            {"title": "W3Schools Python Tutorial", "url": "https://www.w3schools.com/python/", "desc": "Interactive Python reference and coding exercises."},
            {"title": "Official Python Tutorial", "url": "https://docs.python.org/3/tutorial/", "desc": "The official documentation guide for Python beginners."}
        ],
        "math": [
            {"title": "Khan Academy Algebra", "url": "https://www.khanacademy.org/math/algebra", "desc": "Comprehensive free video lessons and practice problems."},
            {"title": "OpenStax College Algebra", "url": "https://openstax.org/details/books/college-algebra", "desc": "Free, peer-reviewed, open-source college algebra textbook."}
        ],
        "science": [
            {"title": "Khan Academy Physics", "url": "https://www.khanacademy.org/science/physics", "desc": "Free science lessons and simulations."},
            {"title": "OpenStax Biology 2e", "url": "https://openstax.org/details/books/biology-2e", "desc": "Free open-source biology textbook."}
        ]
    }
    
    query_lower = query.lower()
    matches = []
    for key, items in resources.items():
        if key in query_lower:
            matches.extend(items)
            
    if not matches:
        # Fallback search results
        matches = [
            {"title": f"Wikipedia: {query.capitalize()}", "url": f"https://en.wikipedia.org/wiki/{query.replace(' ', '_')}", "desc": f"Free collaborative encyclopedia entry for {query}."},
            {"title": f"OpenStax Search: {query.capitalize()}", "url": f"https://openstax.org/subjects", "desc": "Peer-reviewed college textbooks, free online for everyone."}
        ]
        
    result_str = f"Free educational resources for '{query}':\n"
    for r in matches:
        result_str += f"- [{r['title']}]({r['url']}): {r['desc']}\n"
        
    return result_str


@mcp.tool()
def calculate_study_pace(weekly_hours: int, difficulty: str) -> str:
    """Calculate the estimated weeks and pace to complete a curriculum.
    
    Args:
        weekly_hours: Number of hours the student can commit per week.
        difficulty: The course difficulty ('beginner', 'intermediate', or 'advanced').
        
    Returns:
        A report summarizing the duration, pace, and tips for the student.
    """
    base_hours = {
        "beginner": 40,
        "intermediate": 80,
        "advanced": 120
    }
    
    diff_lower = difficulty.lower()
    total_hours = base_hours.get(diff_lower, 60)
    
    if weekly_hours <= 0:
        weekly_hours = 1
        
    weeks = int(total_hours / weekly_hours)
    if total_hours % weekly_hours != 0:
        weeks += 1
        
    report = (
        f"Study Pace Report:\n"
        f"- Target Subject Difficulty: {difficulty.capitalize()}\n"
        f"- Estimated Total Effort: {total_hours} hours\n"
        f"- Commitment: {weekly_hours} hours/week\n"
        f"- Expected Duration: {weeks} weeks\n"
        f"- Tip: "
    )
    
    if weekly_hours < 5:
        report += "Try to find small daily chunks of 30 minutes to stay consistent and not lose momentum."
    elif weekly_hours <= 15:
        report += "This is a great, sustainable pace. Dedicate specific blocks on weekends or evenings."
    else:
        report += "This is a high-intensity pace. Make sure to schedule breaks to avoid burnout."
        
    return report


@mcp.tool()
def validate_quiz_answers(user_answers: list[int], correct_answers: list[int]) -> str:
    """Validate multiple choice quiz answers and provide score and review metrics.
    
    Args:
        user_answers: List of option indices chosen by the user.
        correct_answers: List of correct option indices.
        
    Returns:
        A validation result summary.
    """
    total = len(correct_answers)
    if not total:
        return "Error: No questions to validate."
        
    correct_count = 0
    detailed_results = []
    
    for idx, (ua, ca) in enumerate(zip(user_answers, correct_answers)):
        is_correct = (ua == ca)
        if is_correct:
            correct_count += 1
        detailed_results.append(f"Q{idx+1}: User chose option {ua}, Correct was {ca} -> {'Correct' if is_correct else 'Incorrect'}")
        
    score_percentage = int((correct_count / total) * 100)
    
    summary = (
        f"Quiz Performance Summary:\n"
        f"- Score: {correct_count}/{total} ({score_percentage}%)\n"
        f"- Details:\n"
    )
    summary += "\n".join([f"  * {res}" for res in detailed_results])
    
    if score_percentage >= 80:
        summary += "\n\nExcellent work! You have mastered this material."
    elif score_percentage >= 50:
        summary += "\n\nGood effort. Review the incorrect answers and try again."
    else:
        summary += "\n\nNeed improvement. Go back to the study milestones before retaking the quiz."
        
    return summary

if __name__ == "__main__":
    mcp.run()
