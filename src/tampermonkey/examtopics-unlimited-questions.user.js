// ==UserScript==
// @name         ExamTopics Helper
// @namespace    https://github.com/hypn4/examtopics-helper
// @version      2.1
// @description  Remove 50 question limit, auto-reveal solutions, and provide solution controls
// @author       hypn4
// @homepageURL  https://github.com/hypn4/examtopics-helper
// @supportURL   https://github.com/hypn4/examtopics-helper/issues
// @updateURL    https://raw.githubusercontent.com/hypn4/examtopics-helper/main/src/tampermonkey/examtopics-unlimited-questions.user.js
// @downloadURL  https://raw.githubusercontent.com/hypn4/examtopics-helper/main/src/tampermonkey/examtopics-unlimited-questions.user.js
// @match        https://www.examtopics.com/exams/*/view/*
// @match        https://www.examtopics.com/exams/*/*/view/*
// @match        https://www.examtopics.com/exams/*/custom-view/*
// @match        https://www.examtopics.com/exams/*/*/custom-view/*
// @grant        none
// ==/UserScript==

(function() {
    'use strict';

    // ========== Solution Control Functions ==========

    function revealAllSolutions() {
        const buttons = document.querySelectorAll('.reveal-solution');
        buttons.forEach(btn => btn.click());
        console.log(`[ExamTopics Helper] Revealed ${buttons.length} solutions`);
        return buttons.length;
    }

    function hideAllSolutions() {
        const buttons = document.querySelectorAll('.hide-solution');
        buttons.forEach(btn => btn.click());
        console.log(`[ExamTopics Helper] Hidden ${buttons.length} solutions`);
        return buttons.length;
    }

    // ========== UI Control Panel ==========

    function createControlPanel() {
        const panel = document.createElement('div');
        panel.id = 'examtopics-helper-panel';
        panel.innerHTML = `
            <style>
                #examtopics-helper-panel {
                    position: fixed;
                    bottom: 20px;
                    right: 20px;
                    z-index: 10000;
                    display: flex;
                    flex-direction: column;
                    gap: 8px;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                }
                .eth-btn {
                    padding: 10px 16px;
                    border: none;
                    border-radius: 6px;
                    cursor: pointer;
                    font-size: 14px;
                    font-weight: 500;
                    transition: all 0.2s ease;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
                }
                .eth-btn:hover {
                    transform: translateY(-1px);
                    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
                }
                .eth-btn-reveal {
                    background: #4CAF50;
                    color: white;
                }
                .eth-btn-reveal:hover {
                    background: #43A047;
                }
                .eth-btn-hide {
                    background: #FF5722;
                    color: white;
                }
                .eth-btn-hide:hover {
                    background: #E64A19;
                }
                .eth-status {
                    font-size: 11px;
                    color: #666;
                    text-align: center;
                    background: rgba(255,255,255,0.9);
                    padding: 4px 8px;
                    border-radius: 4px;
                }
            </style>
            <button class="eth-btn eth-btn-reveal" id="eth-reveal-btn">Reveal All</button>
            <button class="eth-btn eth-btn-hide" id="eth-hide-btn">Hide All</button>
            <div class="eth-status" id="eth-status">Ready</div>
        `;

        document.body.appendChild(panel);

        document.getElementById('eth-reveal-btn').addEventListener('click', () => {
            const count = revealAllSolutions();
            updateStatus(`Revealed ${count} solutions`);
        });

        document.getElementById('eth-hide-btn').addEventListener('click', () => {
            const count = hideAllSolutions();
            updateStatus(`Hidden ${count} solutions`);
        });

        console.log('[ExamTopics Helper] Control panel created');
    }

    function updateStatus(message) {
        const status = document.getElementById('eth-status');
        if (status) {
            status.textContent = message;
            setTimeout(() => {
                status.textContent = 'Ready';
            }, 3000);
        }
    }

    // ========== Unlimited Questions (custom-view only) ==========

    function unlimitQuestions() {
        const slider = document.getElementById('QuestionCount');
        if (!slider) {
            console.log('[ExamTopics Helper] Slider not found, retrying...');
            setTimeout(unlimitQuestions, 500);
            return;
        }

        const rangeInput = document.querySelector('input[type="number"][max]');
        let totalQuestions = 401;

        if (rangeInput && rangeInput.max) {
            totalQuestions = parseInt(rangeInput.max, 10);
        } else {
            const match = document.body.innerText.match(/Questions in.*?:\s*(\d+)/);
            if (match) {
                totalQuestions = parseInt(match[1], 10);
            }
        }

        console.log(`[ExamTopics Helper] Total questions: ${totalQuestions}`);

        slider.max = totalQuestions;
        slider.value = totalQuestions;

        if (typeof updatePerPageInput === 'function') {
            updatePerPageInput(totalQuestions);
        } else {
            const label = document.querySelector('.question-per-page');
            if (label) {
                label.textContent = totalQuestions;
            }
        }

        console.log(`[ExamTopics Helper] Questions per page set to ${totalQuestions}`);
        slider.style.background = 'linear-gradient(to right, #4CAF50, #8BC34A)';
    }

    // ========== Auto Reveal Solutions ==========

    function autoRevealSolutions() {
        const buttons = document.querySelectorAll('.reveal-solution');
        if (buttons.length === 0) {
            console.log('[ExamTopics Helper] No reveal buttons found yet, retrying...');
            setTimeout(autoRevealSolutions, 500);
            return;
        }

        const count = revealAllSolutions();
        updateStatus(`Auto-revealed ${count} solutions`);
    }

    // ========== Initialization ==========

    function init() {
        const isCustomView = window.location.pathname.includes('custom-view');
        const isViewPage = window.location.pathname.includes('/view/');

        // Create control panel on all view pages
        if (isViewPage || isCustomView) {
            createControlPanel();
        }

        // Unlimited questions only on custom-view pages
        if (isCustomView) {
            unlimitQuestions();
        }

        // Auto-reveal solutions on view pages (with delay for content loading)
        if (isViewPage || isCustomView) {
            setTimeout(autoRevealSolutions, 1000);
        }

        console.log('[ExamTopics Helper] Initialized');
    }

    // Start when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
