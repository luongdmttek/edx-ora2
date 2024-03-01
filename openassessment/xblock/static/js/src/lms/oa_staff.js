/**
 * Interface for staff assessment view.
 *
 * @param {Element} element - The DOM element representing the XBlock.
 * @param {OpenAssessment.Server} server - The interface to the XBlock server.
 * @param {OpenAssessment.BaseView} baseView - Container view.
 */
import ConfirmationAlert from './oa_confirmation_alert';
export class StaffView {
  constructor(element, server, baseView) {
    this.element = element;
    this.server = server;
    this.baseView = baseView;
    this.isRendering = false;
    this.announceStatus = false;
  }

  /**
     * Load the staff assessment view.
     * */
  load(usageID) {
    const view = this;
    const stepID = '.step--staff-assessment';
    const focusID = `[id='oa_staff_grade_${usageID}']`;
    view.isRendering = true;

    this.server.render('staff_assessment').done(
      (html) => {
        $('.step--staff-assessment', view.element).replaceWith(html);
        view.isRendering = false;
        view.installHandlers();
        view.baseView.announceStatusChangeToSRandFocus(stepID, usageID, false, view, focusID);
      },
    ).fail(() => {
      view.baseView.showLoadError('staff-assessment');
    });
  }

  /**
    Install event handlers for the view.
    * */
  installHandlers() {
    // Install a click handler for collapse/expand
    const sel = $('.step--staff-assessment');
    const view = this;
    this.baseView.setUpCollapseExpand(sel);

    // Install a click handler for the reset button
    sel.find('.staff-waiting__retry_assessment_button').click(
      (eventObject) => {
        // Override default form submission
        eventObject.preventDefault();
        // Obtain the values from the button's data attributes and store in an object
        let values = {
          userid: $(eventObject.target).data('userid'),
        };
        view.handleResetClicked(values);
        
      },
    );
    this.confirmationDialog = new ConfirmationAlert(sel.find('.staff-grade__dialog-confirm'));
  }

  resetEnabled(enabled) {
    this.baseView.buttonEnabled('.staff-waiting__retry_assessment_button', enabled);
  }

  // Call to server Student reset assessment fuction
  selfReset(data){
    this.server.resetStudentAssessment(data)
      .done(() => {
        // Refreshing window
        window.location.reload(true);
      })
      .fail((errCode, errMsg) => {
        console.log(errMsg);
      });
  }

  /**
     Handler for the reset button
  * */
  handleResetClicked(userid) {

    // Immediately disable the reset button to prevent multiple click
    this.resetEnabled(false)

    const view = this;
    const title = gettext('Confirm Reset Submission');
    const msg = gettext('Are you want to reset your response for this assignment ?');

    this.confirmationDialog.confirm(
      title,
      msg,
      () => {
        // Handle the click and send the object to your function
        view.selfReset(userid);
      },
      () => view.resetEnabled(true),
    );
  }
}

export default StaffView;
