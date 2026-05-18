import UIKit

class LocalizedViewController: UIViewController {
    private let titleLabel = UILabel()
    private let actionButton = UIButton()

    override func viewDidLoad() {
        super.viewDidLoad()
        // Properly localised
        titleLabel.text = NSLocalizedString("welcome_title", comment: "")
        actionButton.setTitle(NSLocalizedString("ok_button", comment: ""), for: .normal)
        actionButton.setTitle(String(localized: "cancel_button"), for: .highlighted)
    }
}
