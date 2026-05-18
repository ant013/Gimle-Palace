import UIKit

final class LegacyController: UIViewController {
    var onTap: ((String) -> Void)?
    private let button = UIButton(type: .system)

    override func viewDidLoad() {
        super.viewDidLoad()
        button.addAction(
            UIAction { [weak self] _ in
                self?.onTap?("tap")
            },
            for: .touchUpInside
        )
    }
}
