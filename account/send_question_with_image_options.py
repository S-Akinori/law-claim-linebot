from linebot.models import *
from urllib.parse import quote
from function.render_teplate import extract_placeholders, render_template, fetch_data_for_template

def send_question_with_image_options(api, reply_token, question, options, account_id):
    placeholders = extract_placeholders(question["text"])
    data = fetch_data_for_template(placeholders, account_id)
    rendered = render_template(question["text"], data)
    messages = [TextSendMessage(text=rendered)]
    columns = []
    text_options = []

    for opt in options:
        
        if opt['image_url']:
            columns.append(
                ImageCarouselColumn(
                    image_url=opt['image_url'],
                    action=PostbackAction(
                        label=opt["text"],
                        display_text=opt["text"],
                        data=f"option_id={opt['id']}&question_id={question['id']}&response={quote(opt['text'])}"
                    )
                )
            )
        else:
            text_options.append(
                PostbackAction(
                    label=opt["text"],
                    display_text=opt["text"],
                    data=f"option_id={opt['id']}&question_id={question['id']}&response={quote(opt['text'])}"
                )
            )

    if columns:
        messages.append(
            TemplateSendMessage(
                alt_text=question["title"],
                template=ImageCarouselTemplate(columns=columns)
            )
        )
    elif text_options:
        messages.append(
            TemplateSendMessage(
                alt_text=question["title"],
                template=ButtonsTemplate(
                    text=question["text"],
                    actions=text_options
                )
            )
        )
    api.reply_message(reply_token, messages)