from datetime import datetime, timedelta
import pytz
from openassessment.management.commands.create_oa_submissions_from_file import Command
from django.http import HttpResponse


def assessment_retry_max_time(api_data):
    """
    This function takes an api_data object, extracts num_hour, num_min, and submission_datetime from it,
    converts num_hour and num_min to seconds to create a timedelta, which is then added to submission_datetime.
    If the resulting datetime is greater than the current datetime, the function returns True, otherwise, it returns False.
    
    :param api_data (object): The object containing necessary data, including config_data and submission_data.
    :return: bool: True if the resulting datetime is in the future, False if it is in the past or present
    
    """
    config_data = api_data.config_data
    submission_data = api_data.submission_data

    #submission_data.editor_assessments_order

    # Disable retry option if current datetime it is higher than ora due datetime
    try:
        ora_due_date = datetime.strptime(config_data.submission_due, "%Y-%m-%dT%H:%M:%S%z")
    except:
        ora_due_date = datetime.strptime(config_data.submission_due, "%Y-%m-%dT%H:%M")

    current_datetime = datetime.now(pytz.UTC)
    ora_due_date = ora_due_date.replace(tzinfo=pytz.UTC)
    if current_datetime >= ora_due_date:
        return False

    # Enable retry option if the retry period is higher than current datetime
    num_hour = config_data.openassessment_retry_hours 
    num_min = config_data.openassessment_retry_minutes
    try:
        student_submission_datetime = submission_data.student_submission['created_at']
        if student_submission_datetime.tzinfo is None:
            student_submission_datetime = student_submission_datetime.replace(tzinfo=pytz.UTC)
    except:
        return False

    delta_time = timedelta(hours=int(num_hour), minutes=int(num_min))
    retry_period = student_submission_datetime + delta_time
    
    print('====================================================================')
    print('current_datetime: ', current_datetime)
    print('ora_due_date: ', ora_due_date)
    print(current_datetime >= ora_due_date)
    print('student_submission_datetime: ', student_submission_datetime)
    print('delta_time: ', delta_time)
    print('retry_period: ', retry_period)

    return retry_period > current_datetime


def workflow_status_handler(api_data):
    """
    Determines the workflow status of a student's response based on whether it 
    has been graded by peers, staff, or not at all.
    
    :param: api_data (object): Contains workflow data including status details.
    :return: bool: True if the student's response hasn't been graded by peers or staff, 
          False otherwise.
    """
    workflow_data = api_data.workflow_data
    status_details = workflow_data.status_details
    training_guard, self_guard, peer_guard, staff_guard = True, True, True, True

    # Check if the student has not graded or been graded by another 
    if workflow_data.has_status:
        if 'peer' in workflow_data.status_details:
            if status_details['peer']['peers_graded_count'] != 0 or \
                status_details['peer']['graded_by_count'] != None:
                if status_details['peer']['graded_by_count'] == 0:
                    pass
                else:
                    peer_guard = False

        # Check if the staff has not graded the student
        if workflow_data.status == "done":
            staff_guard = False
    else:
        return False

    return (self_guard and peer_guard and staff_guard and training_guard)


def retry_assessment_enable(api_data):
    """
    Determines if a student's assessment can be retried based on time and workflow status criteria.

    This function combines the results of both the assessment_retry_max_time and workflow_status_handler functions
    to decide if a student's assessment can be retried. The assessment is eligible for retry if the allowed retry
    period is still valid (not expired) and the assessment has not been graded by either peers or staff.

    :param api_data (object): The object containing necessary data for time and workflow status checks.
    :return: bool: True if the student's assessment is eligible for retry, False otherwise.
    """
    time_handler = assessment_retry_max_time(api_data)
    workflow_handler = workflow_status_handler(api_data)

    return (time_handler and workflow_handler)