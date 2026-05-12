import UIKit

class HardcodedViewController: UIViewController {
    private let titleLabel = UILabel()
    private let actionButton = UIButton()

    override func viewDidLoad() {
        super.viewDidLoad()
        titleLabel.text = "Welcome"
        actionButton.setTitle("OK", for: .normal)
    }
}
