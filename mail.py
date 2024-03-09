import transformers
import re
from azure.communication.email import EmailClient
from dotenv import load_dotenv
import os

load_dotenv()



def generate_response(model, tokenizer, system_input, user_input):

    # Format the input using the provided template
    prompt = f"### System:\n{system_input}\n### User:\n{user_input}\n### Assistant:\n"

    # Tokenize and encode the prompt
    inputs = tokenizer.encode(prompt, return_tensors="pt", add_special_tokens=False)

    # Generate a response
    outputs = model.generate(inputs, max_length=10000, num_return_sequences=1)
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)

    # Extract only the assistant's response
    return response.split("### Assistant:\n")[-1]

def prompt_remover(string):
    pattern = r'\*{3}(.*?)\*{3}'  
    return re.findall(pattern, string)

def extract_content(string):
    pattern = r'(\w+)\(\"(.*?)\"\)'
    match = re.match(pattern, string)
    if match:
        return match.groups()
    else:
        return None


def sendmail(recipent,subject,content):
    try:

        connection_string = os.getenv('CONNECTION_STRING')
        client = EmailClient.from_connection_string(connection_string)
        print(connection_string)
        message = {
            "senderAddress": "DoNotReply@07ddf0c0-e4bf-4093-8d55-396d8c1cbd30.azurecomm.net",
            "recipients":  {
                "to": [{"address": recipent }],
            },
            "content": {
                "subject": subject,
                "plainText": content,
            }
        }

        poller = client.begin_send(message)
        result = poller.result()

    except Exception as ex:
        print(ex)

def assess(user_input, model, tokenizer):
    template = '''***official("Johnny showed unprofessional behavior at the beginning of the call by using inappropriate language and taking a long time, later he gave a contact information.")***'''

    system_input = f'''You are the customer service supervisor. You should look at call transcripts and then see if there is any issue. if there is a issue in product you should say "{template}". if there is a issue with the customer service official you should say "***official("the problem description")***" . like what you say using the before rules must be enclosed with three asterisks before and after. the problem description between the parantheses be very much elaborate with details in explaining the problem and why it happened '''
    response = generate_response(model, tokenizer, system_input, user_input)
    queries = prompt_remover(response)
    print(response)
    print(queries)
    for i in queries:
        task, content = extract_content(i)
        if (task=='official'):
            sendmail('nabothdemetrius@gmail.com', 'Issue regarding customer service', content)
            
            
