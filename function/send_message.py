from utils import get_email_template, render_template_with_answers, send_email_via_mailtrap


def send_final_email(user_id: str, account: dict, email_template_id: str):
    template = get_email_template(email_template_id)
    # to_email = get_user_answer_response(user_id, account["id"], account["email_answer_question_id"])
    
    main_email = account["email"]
    sub_emails = account["sub_emails"]
    to_emails = []
    if main_email:
        to_emails.append(main_email)
    if sub_emails: 
        for email in sub_emails:
            to_emails.append(email)
    
    if not main_email:
        return

    subject = render_template_with_answers(template["subject"], user_id, account["id"])
    body = render_template_with_answers(template["body"], user_id, account["id"])
    
    for to_email in to_emails:
        send_email_via_mailtrap(to_email, subject, body)