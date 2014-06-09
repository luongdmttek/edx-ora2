"""
Public interface for student training:

* Staff can create assessments for example responses.
* Students assess an example response, then compare the scores
    they gave to to the instructor's assessment.

"""
import logging
from django.utils.translation import ugettext as _
from django.db import DatabaseError
from submissions import api as sub_api
from openassessment.assessment.models import StudentTrainingWorkflow
from openassessment.assessment.serializers import (
    deserialize_training_examples, serialize_training_example,
    validate_training_example_format,
    InvalidTrainingExample, InvalidRubric
)
from openassessment.assessment.errors import (
    StudentTrainingRequestError, StudentTrainingInternalError
)


logger = logging.getLogger(__name__)


def submitter_is_finished(submission_uuid, requirements):   # pylint:disable=W0613
    """
    Check whether the student has correctly assessed
    all the training example responses.

    Args:
        submission_uuid (str): The UUID of the student's submission.
        requirements (dict): Must contain "num_required" indicating
            the number of examples the student must assess.

    Returns:
        bool

    Raises:
        StudentTrainingRequestError

    """
    try:
        num_required = int(requirements['num_required'])
    except KeyError:
        raise StudentTrainingRequestError(u'Requirements dict must contain "num_required" key')
    except ValueError:
        raise StudentTrainingRequestError(u'Number of requirements must be an integer')

    try:
        workflow = StudentTrainingWorkflow.objects.get(submission_uuid=submission_uuid)
    except StudentTrainingWorkflow.DoesNotExist:
        return False
    else:
        return workflow.num_completed >= num_required


def on_start(submission_uuid):
    """
    Creates a new student training workflow.

    This function should be called to indicate that a submission has entered the
    student training workflow part of the assessment process.

    Args:
        submission_uuid (str): The submission UUID for the student that is
            initiating training.

    Returns:
        None

    Raises:
        StudentTrainingInternalError: Raised when an error occurs persisting the
            Student Training Workflow
    """
    try:
        StudentTrainingWorkflow.create_workflow(submission_uuid)
    except Exception:
        msg = (
            u"An internal error has occurred while creating the student "
            u"training workflow for submission UUID {}".format(submission_uuid)
        )
        logger.exception(msg)
        raise StudentTrainingInternalError(msg)


def validate_training_examples(rubric, examples):
    """
    Validate that the training examples match the rubric.

    Args:
        rubric (dict): Serialized rubric model.
        examples (list): List of serialized training examples.

    Returns:
        list of errors (unicode)

    Raises:
        StudentTrainingRequestError
        StudentTrainingInternalError

    Example usage:

        >>> options = [
        >>>     {
        >>>         "order_num": 0,
        >>>         "name": "poor",
        >>>         "explanation": "Poor job!",
        >>>         "points": 0,
        >>>     },
        >>>     {
        >>>         "order_num": 1,
        >>>         "name": "good",
        >>>         "explanation": "Good job!",
        >>>         "points": 1,
        >>>     },
        >>>     {
        >>>         "order_num": 2,
        >>>         "name": "excellent",
        >>>         "explanation": "Excellent job!",
        >>>         "points": 2,
        >>>     },
        >>> ]
        >>>
        >>> rubric = {
        >>>     "prompt": "Write an essay!",
        >>>     "criteria": [
        >>>         {
        >>>             "order_num": 0,
        >>>             "name": "vocabulary",
        >>>             "prompt": "How varied is the vocabulary?",
        >>>             "options": options
        >>>         },
        >>>         {
        >>>             "order_num": 1,
        >>>             "name": "grammar",
        >>>             "prompt": "How correct is the grammar?",
        >>>             "options": options
        >>>         }
        >>>     ]
        >>> }
        >>>
        >>> examples = [
        >>>     {
        >>>         'answer': u'Lorem ipsum',
        >>>         'options_selected': {
        >>>             'vocabulary': 'good',
        >>>             'grammar': 'excellent'
        >>>         }
        >>>     },
        >>>     {
        >>>         'answer': u'Doler',
        >>>         'options_selected': {
        >>>             'vocabulary': 'good',
        >>>             'grammar': 'poor'
        >>>         }
        >>>     }
        >>> ]
        >>>
        >>> errors = validate_training_examples(rubric, examples)

    """
    errors = []

    # Construct a list of valid options for each criterion
    try:
        criteria_options = {
            unicode(criterion['name']): [
                unicode(option['name'])
                for option in criterion['options']
            ]
            for criterion in rubric['criteria']
        }
    except (ValueError, KeyError):
        logger.warning("Could not parse serialized rubric", exc_info=True)
        return [_(u"Could not parse serialized rubric")]

    # Check each example
    for order_num, example_dict in enumerate(examples, start=1):

        # Check the structure of the example dict
        is_format_valid, format_errors = validate_training_example_format(example_dict)
        if not is_format_valid:
            format_errors = [
                _(u"Example {example_number} has a validation error: {error}").format(
                    example_number=order_num, error=error
                )
                for error in format_errors
            ]
            errors.extend(format_errors)
        else:
            # Check each selected option in the example (one per criterion)
            options_selected = example_dict['options_selected']
            for criterion_name, option_name in options_selected.iteritems():
                if criterion_name in criteria_options:
                    valid_options = criteria_options[criterion_name]
                    if option_name not in valid_options:
                        msg = _(
                            u"Example {example_number} has an invalid option "
                            u"for \"{criterion_name}\": \"{option_name}\""
                        ).format(
                            example_number=order_num,
                            criterion_name=criterion_name,
                            option_name=option_name
                        )
                        errors.append(msg)
                else:
                    msg = _(
                        u"Example {example_number} has an extra option "
                        u"for \"{criterion_name}\""
                    ).format(
                        example_number=order_num,
                        criterion_name=criterion_name
                    )
                    errors.append(msg)

            # Check for missing criteria
            for missing_criterion in set(criteria_options.keys()) - set(options_selected.keys()):
                msg = _(
                    u"Example {example_number} is missing an option "
                    u"for \"{criterion_name}\""
                ).format(
                    example_number=order_num,
                    criterion_name=missing_criterion
                )
                errors.append(msg)

    return errors


def get_num_completed(submission_uuid):
    """
    Get the number of training examples the student has assessed successfully.

    Args:
        submission_uuid (str): The UUID of the student's submission.

    Returns:
        int: The number of completed training examples

    Raises:
        StudentTrainingInternalError

    Example usage:
        >>> get_num_completed("5443ebbbe2297b30f503736e26be84f6c7303c57")
        2

    """
    try:
        try:
            workflow = StudentTrainingWorkflow.objects.get(submission_uuid=submission_uuid)
        except StudentTrainingWorkflow.DoesNotExist:
            return 0
        else:
            return workflow.num_completed
    except DatabaseError:
        msg = (
            u"An unexpected error occurred while "
            u"retrieving the student training workflow status for submission UUID {}"
        ).format(submission_uuid)
        logger.exception(msg)
        raise StudentTrainingInternalError(msg)


def get_training_example(submission_uuid, rubric, examples):
    """
    Retrieve a training example for the student to assess.
    This will implicitly create a workflow for the student if one does not yet exist.

    NOTE: We include the rubric in the returned dictionary to handle
    the case in which the instructor changes the rubric definition
    while the student is assessing the training example.  Once a student
    starts on a training example, the student should see the same training
    example consistently.  However, the next training example the student
    retrieves will use the updated rubric.

    Args:
        submission_uuid (str): The UUID of the student's submission.
        rubric (dict): Serialized rubric model.
        examples (list): List of serialized training examples.

    Returns:
        dict: The training example with keys "answer", "rubric", and "options_selected".
        If no training examples are available (the student has already assessed every example,
            or no examples are defined), returns None.

    Raises:
        StudentTrainingInternalError

    Example usage:

        >>> examples = [
        >>>     {
        >>>         'answer': u'Doler',
        >>>         'options_selected': {
        >>>             'vocabulary': 'good',
        >>>             'grammar': 'poor'
        >>>         }
        >>>     }
        >>> ]
        >>>
        >>> get_training_example("5443ebbbe2297b30f503736e26be84f6c7303c57", rubric, examples)
        {
            'answer': u'Lorem ipsum',
            'rubric': {
                "prompt": "Write an essay!",
                "criteria": [
                    {
                        "order_num": 0,
                        "name": "vocabulary",
                        "prompt": "How varied is the vocabulary?",
                        "options": options
                    },
                    {
                        "order_num": 1,
                        "name": "grammar",
                        "prompt": "How correct is the grammar?",
                        "options": options
                    }
                ],
            },
            'options_selected': {
                'vocabulary': 'good',
                'grammar': 'excellent'
            }
        }

    """
    try:
        # Validate the training examples
        errors = validate_training_examples(rubric, examples)
        if len(errors) > 0:
            msg = (
                u"Training examples do not match the rubric (submission UUID is {uuid}): {errors}"
            ).format(uuid=submission_uuid, errors="\n".join(errors))
            raise StudentTrainingRequestError(msg)

        # Get or create the workflow
        workflow = StudentTrainingWorkflow.get_workflow(submission_uuid=submission_uuid)
        if not workflow:
            raise StudentTrainingRequestError(
                u"No student training workflow found for submission {}".format(submission_uuid)
            )

        # Get or create the training examples
        examples = deserialize_training_examples(examples, rubric)

        # Pick a training example that the student has not yet completed
        # If the student already started a training example, then return that instead.
        next_example = workflow.next_training_example(examples)
        return None if next_example is None else serialize_training_example(next_example)
    except (InvalidRubric, InvalidTrainingExample) as ex:
        logger.exception(
            "Could not deserialize training examples for submission UUID {}".format(submission_uuid)
        )
        raise StudentTrainingRequestError(ex)
    except sub_api.SubmissionNotFoundError as ex:
        msg = u"Could not retrieve the submission with UUID {}".format(submission_uuid)
        logger.exception(msg)
        raise StudentTrainingRequestError(msg)
    except DatabaseError:
        msg = (
            u"Could not retrieve a training example "
            u"for the student with submission UUID {}"
        ).format(submission_uuid)
        logger.exception(msg)
        raise StudentTrainingInternalError(msg)


def assess_training_example(submission_uuid, options_selected, update_workflow=True):
    """
    Assess a training example and update the workflow.

    This must be called *after* `get_training_example()`.

    Args:
        submission_uuid (str): The UUID of the student's submission.
        options_selected (dict): The options the student selected.

    Kwargs:
        update_workflow (bool): If true, mark the current item complete
            if the student has assessed the example correctly.

    Returns:
        corrections (dict): Dictionary containing the correct
            options for criteria the student scored incorrectly.

    Raises:
        StudentTrainingRequestError
        StudentTrainingInternalError

    Example usage:

        >>> options_selected = {
        >>>     'vocabulary': 'good',
        >>>     'grammar': 'excellent'
        >>> }
        >>> assess_training_example("5443ebbbe2297b30f503736e26be84f6c7303c57", options_selected)
        {'grammar': 'poor'}

    """
    # Find a workflow for the student
    try:
        workflow = StudentTrainingWorkflow.objects.get(submission_uuid=submission_uuid)

        # Find the item the student is currently working on
        item = workflow.current_item
        if item is None:
            msg = (
                u"No items are available in the student training workflow associated with "
                u"submission UUID {}"
            ).format(submission_uuid)
            raise StudentTrainingRequestError(msg)

        # Check the student's scores against the staff's scores.
        corrections = item.check(options_selected)

        # Mark the item as complete if the student's selection
        # matches the instructor's selection
        if update_workflow and len(corrections) == 0:
            item.mark_complete()
        return corrections
    except StudentTrainingWorkflow.DoesNotExist:
        msg = u"Could not find student training workflow for submission UUID {}".format(submission_uuid)
        raise StudentTrainingRequestError(msg)
    except DatabaseError:
        msg = (
            u"An error occurred while comparing the student's assessment "
            u"to the training example.  The submission UUID for the student is {}"
        ).format(submission_uuid)
        logger.exception(msg)
        raise StudentTrainingInternalError(msg)