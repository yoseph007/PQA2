
import logging
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTabWidget, QTextBrowser, 
                            QLabel, QScrollArea, QHBoxLayout, QPushButton)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QPixmap, QFont, QIcon

logger = logging.getLogger(__name__)

class HelpTab(QWidget):
    """Help tab with user guide and documentation"""
    
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self._setup_ui()
        
    def _setup_ui(self):
        """Set up the Help tab UI"""
        layout = QVBoxLayout(self)
        
        # Create tabbed interface for different help sections
        help_tabs = QTabWidget()
        
        # Quick Start Guide tab
        quick_start_tab = QWidget()
        quick_start_layout = QVBoxLayout(quick_start_tab)
        
        quick_start_browser = QTextBrowser()
        quick_start_browser.setOpenExternalLinks(True)
        quick_start_browser.setHtml(self._get_quick_start_content())
        quick_start_layout.addWidget(quick_start_browser)
        
        help_tabs.addTab(quick_start_tab, "Quick Start Guide")
        
        # Full User Guide tab
        user_guide_tab = QWidget()
        user_guide_layout = QVBoxLayout(user_guide_tab)
        
        user_guide_browser = QTextBrowser()
        user_guide_browser.setOpenExternalLinks(True)
        user_guide_browser.setHtml(self._get_user_guide_content())
        user_guide_layout.addWidget(user_guide_browser)
        
        help_tabs.addTab(user_guide_tab, "User Guide")
        
        # Installation & Setup tab
        setup_tab = QWidget()
        setup_layout = QVBoxLayout(setup_tab)
        
        setup_browser = QTextBrowser()
        setup_browser.setOpenExternalLinks(True)
        setup_browser.setHtml(self._get_installation_content())
        setup_layout.addWidget(setup_browser)
        
        help_tabs.addTab(setup_tab, "Installation & Setup")
        
        # VMAF Standards tab
        standards_tab = QWidget()
        standards_layout = QVBoxLayout(standards_tab)
        
        standards_browser = QTextBrowser()
        standards_browser.setOpenExternalLinks(True)
        standards_browser.setHtml(self._get_standards_content())
        standards_layout.addWidget(standards_browser)
        
        help_tabs.addTab(standards_tab, "VMAF Standards")
        
        # Troubleshooting tab
        troubleshooting_tab = QWidget()
        troubleshooting_layout = QVBoxLayout(troubleshooting_tab)
        
        troubleshooting_browser = QTextBrowser()
        troubleshooting_browser.setOpenExternalLinks(True)
        troubleshooting_browser.setHtml(self._get_troubleshooting_content())
        troubleshooting_layout.addWidget(troubleshooting_browser)
        
        help_tabs.addTab(troubleshooting_tab, "Troubleshooting")
        
        # Add the tabs to the main layout
        layout.addWidget(help_tabs)
        
    def _get_quick_start_content(self):
        """Get the HTML content for the Quick Start Guide"""
        return """
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; }
                h1 { color: #4CAF50; }
                h2 { color: #2196F3; }
                h3 { color: #673AB7; }
                .step { background-color: #f8f9fa; padding: 10px; margin: 10px 0; border-left: 4px solid #4CAF50; }
                .tip { background-color: #e3f2fd; padding: 10px; margin: 10px 0; border-left: 4px solid #2196F3; }
                .warning { background-color: #fff3e0; padding: 10px; margin: 10px 0; border-left: 4px solid #FF9800; }
            </style>
        </head>
        <body>
            <h1>VMAF Test App - Quick Start Guide</h1>
            
            <p>This guide provides a quick overview of how to perform video quality testing using the VMAF Test App.</p>
            
            <h2>Basic Workflow</h2>
            
            <div class="step">
                <h3>Step 1: Configure Setup</h3>
                <p>In the <b>Setup</b> tab:</p>
                <ul>
                    <li>Enter a test name</li>
                    <li>Select a reference video</li>
                    <li>Choose an output directory for results</li>
                </ul>
            </div>
            
            <div class="step">
                <h3>Step 2: Capture Video</h3>
                <p>In the <b>Capture</b> tab:</p>
                <ul>
                    <li>Select your BlackMagic capture device</li>
                    <li>Configure capture settings</li>
                    <li>Click "Start Capture" to record the video to be tested</li>
                </ul>
            </div>
            
            <div class="step">
                <h3>Step 3: Run Analysis</h3>
                <p>In the <b>Analysis</b> tab:</p>
                <ul>
                    <li>Select a VMAF model (vmaf_v0.6.1 is recommended for general use)</li>
                    <li>Choose an analysis duration</li>
                    <li>Click "Run Analysis" to start the alignment and VMAF processing</li>
                </ul>
            </div>
            
            <div class="step">
                <h3>Step 4: View Results</h3>
                <p>In the <b>Results</b> tab:</p>
                <ul>
                    <li>View the VMAF, PSNR, and SSIM scores</li>
                    <li>Examine detailed metrics and visual comparisons</li>
                    <li>Export results as needed for reporting</li>
                </ul>
            </div>
            
            <div class="tip">
                <h3>Tip: Using Bookend Alignment</h3>
                <p>For the most accurate analysis, use "bookend" alignment method which places bright white flashes at the start and end of your reference video.</p>
            </div>
            
            <div class="warning">
                <h3>Important Note</h3>
                <p>This application is designed to work specifically with BlackMagic capture devices. Other capture hardware may not be compatible.</p>
            </div>
            
            <p>For more detailed information, please see the <b>User Guide</b> tab.</p>
        </body>
        </html>
        """
    
    def _get_user_guide_content(self):
        """Get the HTML content for the User Guide"""
        return """
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; }
                h1 { color: #4CAF50; }
                h2 { color: #2196F3; }
                h3 { color: #673AB7; }
                .section { background-color: #f8f9fa; padding: 10px; margin: 10px 0; border-left: 4px solid #4CAF50; }
                .tip { background-color: #e3f2fd; padding: 10px; margin: 10px 0; border-left: 4px solid #2196F3; }
                .warning { background-color: #fff3e0; padding: 10px; margin: 10px 0; border-left: 4px solid #FF9800; }
                table { border-collapse: collapse; width: 100%; }
                th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                th { background-color: #f2f2f2; }
            </style>
        </head>
        <body>
            <h1>VMAF Test App - Complete User Guide</h1>
            
            <p>This comprehensive guide explains all features and workflows of the VMAF Test App for video quality testing.</p>
            
            <h2>1. Application Overview</h2>
            
            <p>The VMAF (Video Multi-Method Assessment Fusion) Test App is designed to measure the perceived video quality of processed/compressed video compared to original source content. The application uses the following workflow:</p>
            
            <ol>
                <li>Configure test parameters and select a reference video</li>
                <li>Capture the processed/output video using a BlackMagic capture device</li>
                <li>Align the videos to ensure accurate frame comparison</li>
                <li>Run VMAF, PSNR, and SSIM analysis to measure quality</li>
                <li>Present results and export reports</li>
            </ol>
            
            <h2>2. Setup Tab</h2>
            
            <div class="section">
                <h3>Test Configuration</h3>
                <p><b>Test Name:</b> Enter a descriptive name for your test. This will be used in file naming and reports.</p>
                <p><b>Reference Video:</b> Select the original source video for quality comparison.</p>
                <p><b>Output Directory:</b> Choose where test results and reports will be saved.</p>
                
                <h3>Reference Video Preview</h3>
                <p>Once a reference video is selected, you can preview it to ensure it's the correct content.</p>
                <p>The "Generate Bookends" button will create a version of your reference video with white flashes at the beginning and end, which helps with precise alignment.</p>
                
                <h3>Video Information</h3>
                <p>After selecting a reference video, detailed information about the video will be displayed, including resolution, frame rate, duration, and codec details.</p>
            </div>
            
            <h2>3. Capture Tab</h2>
            
            <div class="section">
                <h3>Capture Device Settings</h3>
                <p><b>Capture Device:</b> Select your BlackMagic capture device from the dropdown.</p>
                <p><b>Format:</b> Choose the capture format (resolution and frame rate).</p>
                <p><b>Duration:</b> Set how long to record (in seconds).</p>
                
                <h3>Capture Controls</h3>
                <p><b>Start Capture:</b> Begin recording video from the selected device.</p>
                <p><b>Preview:</b> View the live input from the capture device.</p>
                <p><b>Stop Capture:</b> End the current recording session.</p>
                
                <h3>Captured Video Preview</h3>
                <p>After capture is complete, you can preview the captured video to ensure proper recording.</p>
                <p>The captured video file path will be displayed for reference.</p>
            </div>
            
            <h2>4. Analysis Tab</h2>
            
            <div class="section">
                <h3>Analysis Settings</h3>
                <p><b>VMAF Model:</b> Select the VMAF model to use for analysis. The standard model is vmaf_v0.6.1, but specialized models like vmaf_4k_v0.6.1 are available for specific use cases.</p>
                <p><b>Analysis Duration:</b> Choose how much of the video to analyze (full duration or a specific time period).</p>
                
                <h3>Analysis Process</h3>
                <p>The analysis process consists of two main steps:</p>
                <ol>
                    <li><b>Alignment:</b> The captured video is aligned with the reference video to ensure frame-accurate comparison.</li>
                    <li><b>VMAF Analysis:</b> The aligned videos are analyzed using FFmpeg's libvmaf to calculate VMAF, PSNR, and SSIM metrics.</li>
                </ol>
                
                <h3>Progress Monitoring</h3>
                <p>Both alignment and VMAF analysis progress are displayed with progress bars and status messages.</p>
                <p>A detailed log shows each step of the process for troubleshooting.</p>
            </div>
            
            <h2>5. Results Tab</h2>
            
            <div class="section">
                <h3>Quality Metrics</h3>
                <p><b>VMAF Score:</b> The primary quality metric (0-100), where higher values indicate better quality.</p>
                <p><b>PSNR:</b> Peak Signal-to-Noise Ratio in dB, a traditional quality metric.</p>
                <p><b>SSIM:</b> Structural Similarity Index (0-1), measuring structural differences between images.</p>
                
                <h3>Visual Comparison</h3>
                <p>The Results tab includes visual frame comparisons between reference and captured video to help identify visual differences.</p>
                
                <h3>Export Options</h3>
                <p>Results can be exported in various formats:</p>
                <ul>
                    <li>CSV data for further analysis</li>
                    <li>PDF report with summary and detailed metrics</li>
                    <li>Frame comparison screenshots</li>
                </ul>
            </div>
            
            <h2>6. Options Tab</h2>
            
            <div class="section">
                <h3>General Settings</h3>
                <p>Configure directories, FFmpeg paths, and application appearance.</p>
                
                <h3>Capture Settings</h3>
                <p>Configure capture device parameters and bookend detection settings.</p>
                
                <h3>Analysis Settings</h3>
                <p>Adjust VMAF analysis parameters and alignment methods.</p>
                
                <h3>Customization & Branding</h3>
                <p>Customize application appearance and branding for reports and the UI.</p>
            </div>
            
            <h2>7. Understanding VMAF Scores</h2>
            
            <div class="section">
                <h3>VMAF Scale</h3>
                <p>VMAF scores range from 0 to 100, with higher scores indicating better quality:</p>
                <table>
                    <tr><th>Score Range</th><th>Quality Level</th><th>Typical Use Case</th></tr>
                    <tr><td>90-100</td><td>Excellent</td><td>Visually lossless or near-lossless</td></tr>
                    <tr><td>80-90</td><td>Very Good</td><td>High-quality streaming, premium content</td></tr>
                    <tr><td>70-80</td><td>Good</td><td>Standard streaming quality</td></tr>
                    <tr><td>60-70</td><td>Fair</td><td>Low-bitrate streaming, mobile</td></tr>
                    <tr><td>Below 60</td><td>Poor</td><td>Significant visible degradation</td></tr>
                </table>
                
                <p>Note that VMAF scores should be interpreted within the context of your specific use case and content type.</p>
            </div>
            
            <div class="tip">
                <h3>Best Practices</h3>
                <ul>
                    <li>Always use the bookend alignment method for most accurate results</li>
                    <li>Use the appropriate VMAF model for your content (standard, 4K, etc.)</li>
                    <li>For short content, analyze the full duration; for long content, a representative segment may be sufficient</li>
                    <li>Run multiple tests and average results for more reliable measurements</li>
                </ul>
            </div>
            
            <div class="warning">
                <h3>Known Limitations</h3>
                <ul>
                    <li>VMAF is primarily designed for traditional video content and may not accurately reflect quality for animation, gaming, or specialized content types</li>
                    <li>VMAF scores can be content-dependent; comparisons between different content types should be made cautiously</li>
                    <li>The application requires BlackMagic capture devices and may not work with other capture hardware</li>
                </ul>
            </div>
        </body>
        </html>
        """
    
    def _get_installation_content(self):
        """Get the HTML content for the Installation & Setup tab"""
        return """
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; }
                h1 { color: #4CAF50; }
                h2 { color: #2196F3; }
                h3 { color: #673AB7; }
                .section { background-color: #f8f9fa; padding: 10px; margin: 10px 0; border-left: 4px solid #4CAF50; }
                .code { font-family: monospace; background-color: #f0f0f0; padding: 10px; border-radius: 4px; overflow-x: auto; }
                .note { background-color: #e3f2fd; padding: 10px; margin: 10px 0; border-left: 4px solid #2196F3; }
                .warning { background-color: #fff3e0; padding: 10px; margin: 10px 0; border-left: 4px solid #FF9800; }
            </style>
        </head>
        <body>
            <h1>Installation & Setup Guide</h1>
            
            <p>This guide provides detailed instructions for installing and configuring the VMAF Test App.</p>
            
            <h2>System Requirements</h2>
            
            <div class="section">
                <h3>Hardware Requirements</h3>
                <ul>
                    <li><b>Processor:</b> Intel i5/i7 or AMD Ryzen 5/7 (or equivalent)</li>
                    <li><b>RAM:</b> 8GB minimum, 16GB recommended</li>
                    <li><b>Storage:</b> At least 1GB for the application, plus space for video files</li>
                    <li><b>Video Capture:</b> BlackMagic Design capture device (e.g., Intensity, DeckLink, UltraStudio)</li>
                    <li><b>Display:</b> 1920x1080 resolution minimum</li>
                </ul>
                
                <h3>Software Requirements</h3>
                <ul>
                    <li><b>Operating System:</b> Windows 10/11, macOS 10.15+, or Linux (Ubuntu 20.04+)</li>
                    <li><b>Python:</b> Version 3.8 or higher</li>
                    <li><b>FFmpeg:</b> Version 4.4 or higher with libvmaf support</li>
                    <li><b>BlackMagic Desktop Video:</b> Latest version compatible with your capture device</li>
                    <li><b>Additional dependencies:</b> See below for installation instructions</li>
                </ul>
            </div>
            
            <h2>Installation Steps</h2>
            
            <div class="section">
                <h3>1. Install Python</h3>
                <p>Download and install Python 3.8 or higher from <a href="https://www.python.org/downloads/">python.org</a>.</p>
                <p>Make sure to select "Add Python to PATH" during installation.</p>
                
                <h3>2. Install BlackMagic Desktop Video</h3>
                <p>Download the latest version of BlackMagic Desktop Video for your operating system from <a href="https://www.blackmagicdesign.com/support">BlackMagic Design Support</a>.</p>
                <p>Follow the installation instructions provided by BlackMagic Design.</p>
                
                <h3>3. Install FFmpeg</h3>
                <p>FFmpeg must be installed with libvmaf support for VMAF analysis.</p>
                
                <h4>Windows:</h4>
                <p>Download a pre-built version with libvmaf from <a href="https://www.gyan.dev/ffmpeg/builds/">gyan.dev</a> (use the "full" version).</p>
                <p>Extract the archive and add the bin folder to your system PATH.</p>
                
                <h4>macOS:</h4>
                <div class="code">
                brew install ffmpeg --with-libvmaf
                </div>
                
                <h4>Linux:</h4>
                <div class="code">
                sudo apt update
                sudo apt install ffmpeg libvmaf-dev
                </div>
                
                <h3>4. Download and Install VMAF Test App</h3>
                <p>Clone the repository or download the application package:</p>
                <div class="code">
                git clone https://github.com/your-org/vmaf-test-app.git
                cd vmaf-test-app
                </div>
                
                <p>Create a virtual environment and install dependencies:</p>
                <div class="code">
                python -m venv .venv
                # On Windows:
                .venv\\Scripts\\activate
                # On macOS/Linux:
                source .venv/bin/activate
                
                pip install -r requirements.txt
                </div>
            </div>
            
            <h2>Configuration</h2>
            
            <div class="section">
                <h3>1. First-time Setup</h3>
                <p>Run the application for the first time:</p>
                <div class="code">
                python main.py
                </div>
                
                <p>The application will create default configuration files in your user directory.</p>
                
                <h3>2. Configure Application Settings</h3>
                <p>In the application, navigate to the <b>Options</b> tab to configure:</p>
                <ul>
                    <li>Reference video directory</li>
                    <li>Output directory for test results</li>
                    <li>FFmpeg paths (if not in system PATH)</li>
                    <li>VMAF models directory</li>
                    <li>Capture device settings</li>
                </ul>
                
                <h3>3. Test Your Setup</h3>
                <p>Verify your installation by:</p>
                <ol>
                    <li>Selecting a reference video in the Setup tab</li>
                    <li>Testing your capture device in the Capture tab</li>
                    <li>Running a short VMAF analysis test</li>
                </ol>
                
                <div class="note">
                    <h3>Note on BlackMagic Device Detection</h3>
                    <p>If your BlackMagic device is not detected:</p>
                    <ul>
                        <li>Make sure the device is properly connected and powered</li>
                        <li>Verify BlackMagic Desktop Video is installed correctly</li>
                        <li>Check that you have the latest drivers for your device</li>
                        <li>On Windows, try running the application as Administrator</li>
                    </ul>
                </div>
            </div>
            
            <h2>Updating</h2>
            
            <div class="section">
                <p>To update the application to the latest version:</p>
                <div class="code">
                # Navigate to the application directory
                cd path/to/vmaf-test-app
                
                # Update the repository
                git pull
                
                # Update dependencies
                pip install -r requirements.txt --upgrade
                </div>
            </div>
            
            <div class="warning">
                <h3>Important Note on Dependencies</h3>
                <p>This application is specifically designed to work with BlackMagic capture devices. Other capture hardware is not officially supported and may not work correctly.</p>
                <p>If you encounter issues with device compatibility, please refer to the Troubleshooting tab for guidance.</p>
            </div>
        </body>
        </html>
        """
    
    def _get_standards_content(self):
        """Get the HTML content for the VMAF Standards tab"""
        return """
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; }
                h1 { color: #4CAF50; }
                h2 { color: #2196F3; }
                h3 { color: #673AB7; }
                .section { background-color: #f8f9fa; padding: 10px; margin: 10px 0; border-left: 4px solid #4CAF50; }
                .reference { background-color: #e8f5e9; padding: 10px; margin: 10px 0; border-left: 4px solid #388E3C; }
                table { border-collapse: collapse; width: 100%; }
                th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                th { background-color: #f2f2f2; }
            </style>
        </head>
        <body>
            <h1>VMAF Standards & Industry Practices</h1>
            
            <p>This section provides information about VMAF, industry standards for video quality testing, and best practices.</p>
            
            <h2>About VMAF</h2>
            
            <div class="section">
                <p>Video Multi-Method Assessment Fusion (VMAF) is a perceptual video quality assessment algorithm developed by Netflix in collaboration with the University of Southern California and the Laboratory for Image and Video Engineering at The University of Texas at Austin.</p>
                
                <p>VMAF combines multiple quality metrics and video features using machine learning to predict subjective quality scores that correlate with human perception.</p>
                
                <h3>Key Characteristics</h3>
                <ul>
                    <li>Designed to capture perceptual quality as experienced by viewers</li>
                    <li>Trained on extensive datasets of human subjective quality ratings</li>
                    <li>Outputs scores on a scale from 0 to 100, where higher values indicate better quality</li>
                    <li>More accurately reflects human perception than traditional metrics like PSNR</li>
                    <li>Updated through multiple versions with various optimization targets (standard, 4K, phone, etc.)</li>
                </ul>
            </div>
            
            <h2>VMAF Models</h2>
            
            <div class="section">
                <p>Different VMAF models exist for specific use cases:</p>
                
                <table>
                    <tr>
                        <th>Model</th>
                        <th>Recommended Use</th>
                        <th>Notes</th>
                    </tr>
                    <tr>
                        <td>vmaf_v0.6.1</td>
                        <td>General-purpose testing</td>
                        <td>The standard model, suitable for most content</td>
                    </tr>
                    <tr>
                        <td>vmaf_4k_v0.6.1</td>
                        <td>4K/UHD content</td>
                        <td>Optimized for higher resolution content</td>
                    </tr>
                    <tr>
                        <td>vmaf_b_v0.6.3</td>
                        <td>Broadcast content</td>
                        <td>Tuned for broadcast applications</td>
                    </tr>
                    <tr>
                        <td>vmaf_v0.6.1neg</td>
                        <td>Content with significant artifacts</td>
                        <td>Better at handling severe compression artifacts</td>
                    </tr>
                </table>
                
                <h3>Interpreting VMAF Scores</h3>
                <p>Industry standard interpretations of VMAF scores:</p>
                
                <table>
                    <tr>
                        <th>Score Range</th>
                        <th>Quality Level</th>
                        <th>Typical Viewer Experience</th>
                    </tr>
                    <tr>
                        <td>90-100</td>
                        <td>Excellent</td>
                        <td>Imperceptible or barely perceptible difference from reference</td>
                    </tr>
                    <tr>
                        <td>80-89</td>
                        <td>Very Good</td>
                        <td>Perceptible but not annoying differences</td>
                    </tr>
                    <tr>
                        <td>70-79</td>
                        <td>Good</td>
                        <td>Slightly annoying differences</td>
                    </tr>
                    <tr>
                        <td>60-69</td>
                        <td>Fair</td>
                        <td>Annoying differences</td>
                    </tr>
                    <tr>
                        <td>40-59</td>
                        <td>Poor</td>
                        <td>Very annoying differences</td>
                    </tr>
                    <tr>
                        <td>0-39</td>
                        <td>Very Poor</td>
                        <td>Unwatchable</td>
                    </tr>
                </table>
            </div>
            
            <h2>Industry Standards & Testing Protocols</h2>
            
            <div class="section">
                <h3>Recommended Testing Practices</h3>
                
                <h4>1. Test Selection</h4>
                <ul>
                    <li>Use diverse content types (sports, drama, animation, etc.)</li>
                    <li>Include challenging scenes (fast motion, dark scenes, detailed textures)</li>
                    <li>Test with varying resolutions and frame rates</li>
                </ul>
                
                <h4>2. Test Methodology</h4>
                <ul>
                    <li>Use consistent test conditions across comparisons</li>
                    <li>Ensure proper video alignment (frame-accurate)</li>
                    <li>Use appropriate VMAF model for content type and viewing conditions</li>
                    <li>Run multiple tests and average results</li>
                </ul>
                
                <h4>3. Reporting</h4>
                <ul>
                    <li>Document test conditions (hardware, software, settings)</li>
                    <li>Include both average scores and per-scene analysis</li>
                    <li>Report confidence intervals or variance in measurements</li>
                    <li>Provide visual examples for context</li>
                </ul>
                
                <h3>Related Industry Standards</h3>
                <ul>
                    <li><b>ITU-T P.910:</b> Subjective video quality assessment methods for multimedia applications</li>
                    <li><b>ITU-R BT.500:</b> Methodology for subjective assessment of video quality</li>
                    <li><b>ITU-T J.144:</b> Objective perceptual video quality measurement techniques</li>
                    <li><b>VQEG (Video Quality Experts Group):</b> Testing methodologies and validation procedures</li>
                </ul>
            </div>
            
            <h2>Best Practices for VMAF Testing</h2>
            
            <div class="section">
                <h3>1. Accurate Alignment</h3>
                <p>Proper temporal alignment between reference and test videos is critical for accurate VMAF measurements. The bookend approach (white flashes at start/end) provides the most precise alignment.</p>
                
                <h3>2. Representative Sampling</h3>
                <p>For long content, select representative segments that include various visual characteristics (motion, detail, color variance).</p>
                
                <h3>3. Multiple Metrics</h3>
                <p>While VMAF is a powerful metric, also consider PSNR and SSIM for a more complete understanding of video quality differences.</p>
                
                <h3>4. Context-Specific Evaluation</h3>
                <p>Interpret results in the context of your specific use case - acceptable quality thresholds may differ between broadcast, streaming, and archival applications.</p>
                
                <h3>5. Hardware Considerations</h3>
                <p>Ensure that capture hardware does not introduce artifacts that could affect measurements. Use high-quality BlackMagic capture devices with appropriate settings.</p>
            </div>
            
            <div class="reference">
                <h3>Further Reading</h3>
                <ul>
                    <li><a href="https://github.com/Netflix/vmaf">Netflix VMAF GitHub Repository</a></li>
                    <li><a href="https://netflixtechblog.com/vmaf-the-journey-continues-44b51ee9ed12">Netflix Tech Blog: VMAF - The Journey Continues</a></li>
                    <li><a href="https://www.itu.int/rec/T-REC-P.910/en">ITU-T P.910 Recommendation</a></li>
                    <li><a href="https://www.itu.int/rec/R-REC-BT.500/en">ITU-R BT.500 Recommendation</a></li>
                    <li><a href="https://www.vqeg.org/">Video Quality Experts Group</a></li>
                </ul>
            </div>
        </body>
        </html>
        """
    
    def _get_troubleshooting_content(self):
        """Get the HTML content for the Troubleshooting tab"""
        return """
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; }
                h1 { color: #4CAF50; }
                h2 { color: #2196F3; }
                h3 { color: #673AB7; }
                .issue { background-color: #f8f9fa; padding: 10px; margin: 10px 0; border-left: 4px solid #F44336; }
                .solution { background-color: #e8f5e9; padding: 10px; margin: 5px 0 15px 20px; border-left: 4px solid #4CAF50; }
                .code { font-family: monospace; background-color: #f0f0f0; padding: 10px; border-radius: 4px; overflow-x: auto; }
            </style>
        </head>
        <body>
            <h1>Troubleshooting Guide</h1>
            
            <p>This guide helps resolve common issues with the VMAF Test App.</p>
            
            <h2>Capture Device Issues</h2>
            
            <div class="issue">
                <h3>BlackMagic device not detected</h3>
                <p>The application cannot find or initialize your BlackMagic capture device.</p>
                
                <div class="solution">
                    <h4>Solutions:</h4>
                    <ol>
                        <li>Verify the device is properly connected and powered</li>
                        <li>Ensure BlackMagic Desktop Video is installed correctly</li>
                        <li>Check for driver updates from BlackMagic</li>
                        <li>On Windows, run the application as Administrator</li>
                        <li>Try restarting your computer</li>
                        <li>Verify the device works in BlackMagic Media Express</li>
                    </ol>
                </div>
            </div>
            
            <div class="issue">
                <h3>Capture fails to start</h3>
                <p>The application cannot start the capture process.</p>
                
                <div class="solution">
                    <h4>Solutions:</h4>
                    <ol>
                        <li>Check if another application is using the capture device</li>
                        <li>Try selecting a different format in the Capture tab</li>
                        <li>Verify the selected output directory is writable</li>
                        <li>Check the application logs for specific error messages</li>
                    </ol>
                </div>
            </div>
            
            <div class="issue">
                <h3>Poor quality or distorted capture</h3>
                <p>The captured video has artifacts, distortion, or incorrect colors.</p>
                
                <div class="solution">
                    <h4>Solutions:</h4>
                    <ol>
                        <li>Verify input signal matches the selected capture format</li>
                        <li>Check cables and connections</li>
                        <li>Try a different pixel format setting</li>
                        <li>Make sure the source device is outputting a clean signal</li>
                    </ol>
                </div>
            </div>
            
            <h2>Analysis Issues</h2>
            
            <div class="issue">
                <h3>Alignment fails</h3>
                <p>The application cannot properly align the reference and captured videos.</p>
                
                <div class="solution">
                    <h4>Solutions:</h4>
                    <ol>
                        <li>Use the bookend method with white flashes for more reliable alignment</li>
                        <li>Make sure the captured video includes the complete content</li>
                        <li>Adjust bookend detection settings in the Options tab</li>
                        <li>Try manual alignment if automated methods fail</li>
                    </ol>
                </div>
            </div>
            
            <div class="issue">
                <h3>VMAF analysis fails</h3>
                <p>The VMAF analysis process fails to complete or returns errors.</p>
                
                <div class="solution">
                    <h4>Solutions:</h4>
                    <ol>
                        <li>Verify FFmpeg is installed correctly with libvmaf support</li>
                        <li>Check that the VMAF models are in the correct directory</li>
                        <li>Try using a different VMAF model</li>
                        <li>Analyze a shorter segment of video</li>
                        <li>Check the application logs for specific FFmpeg errors</li>
                    </ol>
                    
                    <p>To verify FFmpeg has libvmaf support, run:</p>
                    <div class="code">ffmpeg -filters | grep vmaf</div>
                    <p>This should show the libvmaf filter in the output.</p>
                </div>
            </div>
            
            <div class="issue">
                <h3>Missing PSNR or SSIM results</h3>
                <p>VMAF results appear but PSNR and/or SSIM metrics are missing.</p>
                
                <div class="solution">
                    <h4>Solutions:</h4>
                    <ol>
                        <li>Make sure the "Save JSON Results" option is enabled in the Options tab</li>
                        <li>Verify your FFmpeg version supports combined VMAF/PSNR/SSIM analysis</li>
                        <li>Try updating to the latest FFmpeg version</li>
                    </ol>
                </div>
            </div>
            
            <div class="issue">
                <h3>Duplicate analysis results</h3>
                <p>The analysis runs twice or produces duplicate results.</p>
                
                <div class="solution">
                    <h4>Solutions:</h4>
                    <ol>
                        <li>Wait for the first analysis to complete before starting a new one</li>
                        <li>If the issue persists, restart the application</li>
                        <li>Check for multiple instances of the application running</li>
                    </ol>
                </div>
            </div>
            
            <h2>Application Issues</h2>
            
            <div class="issue">
                <h3>Application crashes or freezes</h3>
                <p>The application becomes unresponsive or closes unexpectedly.</p>
                
                <div class="solution">
                    <h4>Solutions:</h4>
                    <ol>
                        <li>Check system resources (memory, CPU usage)</li>
                        <li>Verify all dependencies are properly installed</li>
                        <li>Make sure your Python version is compatible (3.8+)</li>
                        <li>Check logs for error messages before the crash</li>
                        <li>Try updating to the latest version of the application</li>
                    </ol>
                </div>
            </div>
            
            <div class="issue">
                <h3>UI elements missing or misaligned</h3>
                <p>Application interface appears broken or incomplete.</p>
                
                <div class="solution">
                    <h4>Solutions:</h4>
                    <ol>
                        <li>Verify PyQt5 is properly installed</li>
                        <li>Try resetting the application settings in the Options tab</li>
                        <li>Make sure your display resolution meets minimum requirements</li>
                        <li>Try changing the theme setting</li>
                    </ol>
                </div>
            </div>
            
            <div class="issue">
                <h3>Settings not saving</h3>
                <p>Configuration changes in the Options tab don't persist after restart.</p>
                
                <div class="solution">
                    <h4>Solutions:</h4>
                    <ol>
                        <li>Make sure to click "Save Settings" after making changes</li>
                        <li>Check if the application has write permissions to its config directory</li>
                        <li>Verify the settings file isn't set to read-only</li>
                    </ol>
                </div>
            </div>
            
            <h2>FFmpeg Issues</h2>
            
            <div class="issue">
                <h3>FFmpeg not found</h3>
                <p>The application cannot locate the FFmpeg executables.</p>
                
                <div class="solution">
                    <h4>Solutions:</h4>
                    <ol>
                        <li>Make sure FFmpeg is installed and in your system PATH</li>
                        <li>Manually specify the FFmpeg path in the Options tab</li>
                        <li>On Windows, ensure you're using the correct ffmpeg.exe, ffprobe.exe, and ffplay.exe paths</li>
                    </ol>
                </div>
            </div>
            
            <div class="issue">
                <h3>Missing libvmaf support</h3>
                <p>FFmpeg is found but doesn't have libvmaf support.</p>
                
                <div class="solution">
                    <h4>Solutions:</h4>
                    <ol>
                        <li>Install a version of FFmpeg compiled with libvmaf support</li>
                        <li>On Windows, download a pre-built version from gyan.dev (use the "full" build)</li>
                        <li>On Linux, install additional packages: <code>sudo apt install libvmaf-dev</code></li>
                        <li>On macOS: <code>brew install ffmpeg --with-libvmaf</code></li>
                    </ol>
                </div>
            </div>
            
            <h2>Getting Help</h2>
            
            <p>If you're still experiencing issues after trying the solutions above:</p>
            
            <ol>
                <li>Check the application logs (in the 'logs' directory)</li>
                <li>Take screenshots of any error messages</li>
                <li>Note your system configuration, including OS, Python version, and FFmpeg version</li>
                <li>Contact technical support with this information</li>
            </ol>
            
            <p>For reporting bugs or requesting features, please visit our project repository.</p>
        </body>
        </html>
        """
