import streamlit as st
from pymongo import MongoClient
from datetime import datetime,date
import time

client = MongoClient(st.secrets['MONGO_URI'])
#db user_data has collections for users, courses, tokens, and archival date. 
db = client["user_data"]

course_collection = db['courses']
users_collection = db["users"]
tokens = db['tokens']
archival_date = db['archival_date']
#db chat_app for archived chats
archived_chats_db = client['chat_app']
archive_chats_collection = archived_chats_db['chats']
#db model_data for examples and completions
model_db = client['model_data']
model_examples = model_db['examples']
model_completions = model_db['completions']
system_prompts_collection = model_db['system_prompts']
model_name_collection = model_db['model_names']



if 'courses_valid' not in st.session_state: 
    st.session_state.courses_valid = False


def add_examples_to_db(input,output):
    model_examples.insert_one({"bot_type":st.session_state.selected_bot,"input":input,"output":output})

def add_completions_to_db(input,output):
    system_prompt = get_system_prompt()
    completion = {"messages":[{"role":"system","content":system_prompt},{"role":"user","content":input},{"role":"assistant","content":output}]}
    model_completions.insert_one({"bot_type":st.session_state.selected_bot,"messages":completion})

def get_bot_competions(bot_type):
    completions = list(model_completions.find({"bot_type":bot_type},{"_id":0,"messages":1}))
    return completions 
def get_bot_examples(bot_type):
    examples = list(model_examples.find({"bot_type":bot_type},{"_id":0,"input":1,"output":1}))
    return examples
def get_model_name():
    #if nothing is selected default to tutor. If selected model is not in db, then also default to tutor
    tutor_model = get_tutor_model()
    if 'selected_bot' not in st.session_state:
        return tutor_model
    selected_bot = st.session_state.selected_bot
    model_name = model_name_collection.find_one({"course_id":selected_bot})
    if model_name:
        return model_name["model_name"]
    return tutor_model
def get_tutor_model():
     tutor_model = model_name_collection.find_one({"course_id":"tutorbot"})
     return tutor_model["model_name"]

def get_system_prompt():
    #if system prompt does not exist, default to tutorbot
    selected_bot = st.session_state.selected_bot
    system_prompt = system_prompts_collection.find_one({"course_id":selected_bot})
    if system_prompt:
        return system_prompt.get('prompt')
    tutor_prompt = system_prompts_collection.find_one({"course_id":"tutorbot"})
    return tutor_prompt.get('prompt')

def get_current_semester():
    #this is only checked once per session.
    date = datetime.now()
    # date =  date.strftime("%Y-%m-%d")
    year = date.year
    day = date.day
    month = date.month
    semester_type = ""
    if 1<=month <=5:
        if month==5 and day>7:
            semester_type=='Summer'
        semester_type='Spring'
    elif 6<=month<=8:
        semester_type='Summer'
    else:
        semester_type='Fall'
    
    semester = f'{semester_type} {year}'
    return semester
def check_system_down_time():
    date = datetime.now()
    weekday = date.strftime("%A")
    hour = int(date.strftime("%H"))
    #monday, wednesday,friday from 4am to 6am | 
    warning_message = "The IT system is currently under maintenance. Emails will not be sent."
    if (weekday=="Monday" or weekday=='Wednesday' or weekday == 'Friday' ) and 4<=hour<=6:
        st.warning(warning_message)
    #Tuesdays and Thursdays from 12am to 6am
    elif (weekday=="Tuesday" or weekday=='Thursday') and 0<=hour<=6:
        st.warning(warning_message)
    #Saturdays from 8pm to 12 am and Sundays 12am to 12pm
    elif (weekday =='Saturday' and 20<=hour<=23) or weekday=='Sunday' and 0<=hour<=12:
        st.warning(warning_message)

def set_archive_date(set_date):
    #set_date is a date object but we need to make it datetime. Just add a time field with the minimum time 0:0:0 at midnight
    if isinstance(set_date,date):
        set_date = datetime.combine(set_date,datetime.min.time())
    archival_date.update_one({},{"$set":{"archival_date":set_date}})
def get_archive_date():
    archive_date = list(archival_date.find({}))
    return archive_date
def get_courses():
    courses = list(course_collection.find({},{"course_name":1,"course_id":1,"_id":0}))
    return courses
def get_all_chat_fields():
    users = users_collection.find()
    chat_fields = set()
    chat_histories_by_user = []
    semester=  get_current_semester()
    for user in users:
        for field in user:
            if 'chat' in field.lower():
                chat_fields.add(field)
            if 'histories' in field.lower() and 'panther_id' in user:
                chat_histories_by_user.append({"panther_id":user["panther_id"],field:user[field],"semester":semester})
    return list(chat_fields),chat_histories_by_user

def get_user_chat_history(panther_id):
    user = users_collection.find_one({"panther_id":panther_id})
    chat_histories = []
    for field in user:
        if 'histories' in field.lower():
            chat_histories.append({"panther_id":panther_id,field:user[field]})
    return chat_histories

def archive_user_chat_histories(user_chat_histories):
    if user_chat_histories:
        archive_chats_collection.insert_many(user_chat_histories)


def archive_chats():
    #for all users except admins status back to pending_courses, courses array empty, all chat histories and chat_ids removed
    chat_fields, chat_histories_by_user = get_all_chat_fields()
    archive_user_chat_histories(chat_histories_by_user)
    chat_fields_unset = {field: "" for field in chat_fields}
    users_collection.update_many({"user_type":{"$ne":"admin"}},{"$set":{"status":"pending_courses","courses":[]},"$unset":chat_fields_unset})
def get_user_courses(user_id):
        user_doc = users_collection.find_one({'panther_id':user_id})
        user_courses = user_doc.get("courses", [])
        return user_courses

def get_course_dict(course_ids):
    courses = list(course_collection.find({"course_id":{"$in":course_ids}}))
    course_names = {course['course_name']:course['course_id'] for course in courses}
    return course_names
def add_courses_to_student(panther_id,course_ids):
    print('adding courses to student')
    users_collection.update_one({"panther_id":panther_id}, #query
                                {"$push":{"courses":{"$each":course_ids}},
                                 "$set":{"status":"pending_approval"}
                                 }, #update
                                )
    st.success('Course information successfully uploaded')
    st.session_state.status='pending_approval'
    time.sleep(2)
    st.rerun()

def parse_courses(courses):
    #this is to be used in course upload, receving a course array, need to filter out those inside the course collection
    tutored_courses = course_collection.find({
        'course_id' : {"$in":courses}
    })
    return [course["course_id"] for course in tutored_courses]

def get_pending_students():
    students = list(users_collection.find({"user_type":"student","status": "pending_approval"}))
    return students

def get_enrolled_students():
    students = list(users_collection.find({"user_type":"student","status":"approved"}))
    return students
def get_pending_tutors():
    pending_tutors = list(users_collection.find({"user_type":"tutor","status":"pending_approval"}))
    return pending_tutors

def get_enrolled_tutors():
    enrolled_tutors = list(users_collection.find({"user_type":"tutor","status":"approved"}))
    return enrolled_tutors
def find_token():
    token = tokens.find_one()
    return token

def remove_token():
    tokens.delete_many({})


