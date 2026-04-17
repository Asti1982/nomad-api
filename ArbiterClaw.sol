// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract ArbiterClaw {
    address public devWallet;
    address public foundationWallet;

    event ContributionReceived(address indexed user, uint256 amount, uint256 devShare, uint256 foundationShare);
    event ArbitrageVerified(string route, uint256 price, string proofHash);

    constructor(address _devWallet, address _foundationWallet) {
        devWallet = _devWallet;
        foundationWallet = _foundationWallet;
    }

    // Handles the 70/30 funding split
    receive() external payable {
        uint256 foundationAmount = (msg.value * 30) / 100;
        uint256 devAmount = msg.value - foundationAmount;

        (bool s1, ) = devWallet.call{value: devAmount}("");
        (bool s2, ) = foundationWallet.call{value: foundationAmount}("");
        require(s1 && s2, "Split failed");

        emit ContributionReceived(msg.sender, msg.value, devAmount, foundationAmount);
    }

    function recordFinding(string memory route, uint256 price, string memory proofHash) external {
        emit ArbitrageVerified(route, price, proofHash);
    }
}