
import logging
import os

import matplotlib

matplotlib.use('Agg')  # Use non-interactive backend
from datetime import datetime

import matplotlib.pyplot as plt
from PyQt5.QtCore import QObject, QThread, pyqtSignal
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

logger = logging.getLogger(__name__)

class ReportGenerator(QObject):
    """Generates PDF reports for VMAF analysis results"""
    report_progress = pyqtSignal(int)
    report_complete = pyqtSignal(str)
    report_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.styles = getSampleStyleSheet()
        # Create custom styles
        self.styles.add(ParagraphStyle(
            name='Title',
            parent=self.styles['Heading1'],
            fontSize=16,
            spaceAfter=12
        ))
        self.styles.add(ParagraphStyle(
            name='Subtitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=10
        ))
        self.styles.add(ParagraphStyle(
            name='Normal',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=8
        ))

    def generate_report(self, results, test_metadata=None, output_path=None):
        """
        Generate a PDF report for VMAF analysis results
        
        Args:
            results: Dictionary containing VMAF analysis results
            test_metadata: Optional metadata about the test
            output_path: Path where PDF should be saved (default: same directory as results)
        
        Returns:
            Path to generated PDF
        """
        try:
            self.report_progress.emit(10)
            
            # Determine output path if not provided
            if not output_path:
                json_path = results.get('json_path')
                if json_path:
                    output_dir = os.path.dirname(json_path)
                    output_path = os.path.join(output_dir, f"vmaf_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
                else:
                    raise ValueError("No output path provided and no json_path in results")
            
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Extract data from results
            vmaf_score = results.get('vmaf_score', 'N/A')
            psnr_score = results.get('psnr', 'N/A')
            ssim_score = results.get('ssim', 'N/A')
            reference_path = results.get('reference_path', 'N/A')
            distorted_path = results.get('distorted_path', 'N/A')
            
            # Generate frame-level charts if available
            self.report_progress.emit(20)
            chart_paths = []
            if 'raw_results' in results:
                raw_data = results['raw_results']
                chart_paths = self._generate_charts(raw_data, os.path.dirname(output_path))
            
            # Create PDF document
            self.report_progress.emit(40)
            doc = SimpleDocTemplate(output_path, pagesize=A4)
            elements = []
            
            # Add title and metadata
            title = "VMAF Video Quality Analysis Report"
            elements.append(Paragraph(title, self.styles['Title']))
            
            # Add test metadata
            if test_metadata:
                test_name = test_metadata.get('test_name', 'Unknown Test')
                elements.append(Paragraph(f"Test: {test_name}", self.styles['Subtitle']))
                
                metadata_list = [
                    f"Date: {test_metadata.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}",
                    f"Tester: {test_metadata.get('tester_name', 'Unknown')}",
                    f"Location: {test_metadata.get('test_location', 'Unknown')}"
                ]
                
                for item in metadata_list:
                    elements.append(Paragraph(item, self.styles['Normal']))
            
            elements.append(Spacer(1, 0.2*inch))
            
            # Add score summary
            elements.append(Paragraph("Quality Scores", self.styles['Subtitle']))
            
            data = [
                ["Metric", "Value", "Interpretation"],
                ["VMAF", f"{vmaf_score:.2f}" if isinstance(vmaf_score, (int, float)) else vmaf_score, self._interpret_vmaf(vmaf_score)],
                ["PSNR", f"{psnr_score:.2f} dB" if isinstance(psnr_score, (int, float)) else psnr_score, self._interpret_psnr(psnr_score)],
                ["SSIM", f"{ssim_score:.4f}" if isinstance(ssim_score, (int, float)) else ssim_score, self._interpret_ssim(ssim_score)]
            ]
            
            table = Table(data, colWidths=[1.5*inch, 1.5*inch, 3*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ALIGN', (1, 1), (1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            elements.append(table)
            elements.append(Spacer(1, 0.2*inch))
            
            # Add file information
            elements.append(Paragraph("File Information", self.styles['Subtitle']))
            
            ref_name = os.path.basename(reference_path) if reference_path != 'N/A' else 'N/A'
            dist_name = os.path.basename(distorted_path) if distorted_path != 'N/A' else 'N/A'
            
            data = [
                ["File", "Path"],
                ["Reference", ref_name],
                ["Distorted", dist_name]
            ]
            
            table = Table(data, colWidths=[1.5*inch, 4.5*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            elements.append(table)
            elements.append(Spacer(1, 0.2*inch))
            
            # Add charts if available
            self.report_progress.emit(60)
            if chart_paths:
                elements.append(Paragraph("Quality Metrics Over Time", self.styles['Subtitle']))
                
                for chart_path in chart_paths:
                    if os.path.exists(chart_path):
                        img = Image(chart_path, width=6*inch, height=3*inch)
                        elements.append(img)
                        elements.append(Spacer(1, 0.1*inch))
            
            # Add VMAF feature analysis if available
            self.report_progress.emit(80)
            if 'raw_results' in results and 'frames' in results['raw_results']:
                elements.append(Paragraph("VMAF Feature Analysis", self.styles['Subtitle']))
                
                # Extract feature data if available
                frames = results['raw_results']['frames']
                if frames and len(frames) > 0 and 'metrics' in frames[0]:
                    # Take a sample of frames to avoid making the table too large
                    frame_step = max(1, len(frames) // 10)  # Show at most 10 frames
                    sample_frames = frames[::frame_step]
                    
                    # Create table data
                    data = [["Frame", "VMAF", "PSNR", "SSIM"]]
                    
                    for i, frame in enumerate(sample_frames):
                        metrics = frame.get('metrics', {})
                        frame_num = frame.get('frameNum', i*frame_step)
                        vmaf_val = metrics.get('vmaf', 'N/A')
                        psnr_val = metrics.get('psnr', metrics.get('psnr_y', 'N/A'))
                        ssim_val = metrics.get('ssim', metrics.get('ssim_y', 'N/A'))
                        
                        # Format values
                        if isinstance(vmaf_val, (int, float)):
                            vmaf_val = f"{vmaf_val:.2f}"
                        if isinstance(psnr_val, (int, float)):
                            psnr_val = f"{psnr_val:.2f}"
                        if isinstance(ssim_val, (int, float)):
                            ssim_val = f"{ssim_val:.4f}"
                            
                        data.append([str(frame_num), vmaf_val, psnr_val, ssim_val])
                    
                    # Create table
                    table = Table(data, colWidths=[1*inch, 1.5*inch, 1.5*inch, 1.5*inch])
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 10),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black),
                        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('FONTSIZE', (0, 1), (-1, -1), 8)
                    ]))
                    
                    elements.append(table)
            
            # Add certification
            elements.append(Spacer(1, 0.3*inch))
            elements.append(Paragraph("Certification", self.styles['Subtitle']))
            
            cert_text = (
                "I hereby certify that the video quality testing described in this report "
                "was conducted in accordance with industry standards and that the results "
                "presented are accurate to the best of my knowledge."
            )
            elements.append(Paragraph(cert_text, self.styles['Normal']))
            
            # Add signature lines
            elements.append(Spacer(1, 0.5*inch))
            data = [
                ["_______________________", "_______________________"],
                ["Date", "Signature"],
                ["", ""],
                ["", "_______________________"],
                ["", "Name"]
            ]
            
            table = Table(data, colWidths=[3*inch, 3*inch])
            table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LINEABOVE', (0, 0), (0, 0), 1, colors.black),
                ('LINEABOVE', (1, 0), (1, 0), 1, colors.black),
                ('LINEABOVE', (1, 3), (1, 3), 1, colors.black),
            ]))
            
            elements.append(table)
            
            # Build PDF
            self.report_progress.emit(90)
            doc.build(elements)
            
            # Cleanup temporary chart files
            for chart_path in chart_paths:
                try:
                    if os.path.exists(chart_path):
                        os.remove(chart_path)
                except Exception as e:
                    logger.warning(f"Error cleaning up chart file {chart_path}: {e}")
            
            self.report_progress.emit(100)
            self.report_complete.emit(output_path)
            
            return output_path
            
        except Exception as e:
            logger.error(f"Error generating report: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            self.report_error.emit(f"Failed to generate report: {str(e)}")
            return None
    
    def _generate_charts(self, raw_data, output_dir):
        """Generate charts from raw VMAF results data"""
        chart_paths = []
        try:
            # Check if frames data is available
            if 'frames' not in raw_data or not raw_data['frames']:
                return chart_paths
                
            frames = raw_data['frames']
            
            # Extract frame data
            frame_nums = []
            vmaf_scores = []
            psnr_scores = []
            ssim_scores = []
            
            for frame in frames:
                frame_num = frame.get('frameNum', len(frame_nums))
                metrics = frame.get('metrics', {})
                
                frame_nums.append(frame_num)
                vmaf_scores.append(metrics.get('vmaf', None))
                psnr_scores.append(metrics.get('psnr', metrics.get('psnr_y', None)))
                ssim_scores.append(metrics.get('ssim', metrics.get('ssim_y', None)))
            
            # Generate VMAF chart
            if vmaf_scores and any(v is not None for v in vmaf_scores):
                vmaf_path = os.path.join(output_dir, "vmaf_chart.png")
                plt.figure(figsize=(10, 5))
                plt.plot(frame_nums, vmaf_scores, 'b-')
                plt.title('VMAF Score Over Time')
                plt.xlabel('Frame Number')
                plt.ylabel('VMAF Score')
                plt.grid(True, alpha=0.3)
                plt.ylim(0, 100)
                plt.tight_layout()
                plt.savefig(vmaf_path, dpi=100)
                plt.close()
                chart_paths.append(vmaf_path)
            
            # Generate PSNR chart
            if psnr_scores and any(p is not None for p in psnr_scores):
                psnr_path = os.path.join(output_dir, "psnr_chart.png")
                plt.figure(figsize=(10, 5))
                plt.plot(frame_nums, psnr_scores, 'g-')
                plt.title('PSNR Score Over Time')
                plt.xlabel('Frame Number')
                plt.ylabel('PSNR (dB)')
                plt.grid(True, alpha=0.3)
                plt.tight_layout()
                plt.savefig(psnr_path, dpi=100)
                plt.close()
                chart_paths.append(psnr_path)
            
            # Generate SSIM chart
            if ssim_scores and any(s is not None for s in ssim_scores):
                ssim_path = os.path.join(output_dir, "ssim_chart.png")
                plt.figure(figsize=(10, 5))
                plt.plot(frame_nums, ssim_scores, 'r-')
                plt.title('SSIM Score Over Time')
                plt.xlabel('Frame Number')
                plt.ylabel('SSIM')
                plt.grid(True, alpha=0.3)
                plt.ylim(0, 1)
                plt.tight_layout()
                plt.savefig(ssim_path, dpi=100)
                plt.close()
                chart_paths.append(ssim_path)
                
            # Generate combined chart
            combined_path = os.path.join(output_dir, "combined_chart.png")
            fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 10), sharex=True)
            
            # VMAF subplot
            ax1.plot(frame_nums, vmaf_scores, 'b-')
            ax1.set_title('VMAF Score')
            ax1.set_ylabel('VMAF')
            ax1.grid(True, alpha=0.3)
            ax1.set_ylim(0, 100)
            
            # PSNR subplot
            ax2.plot(frame_nums, psnr_scores, 'g-')
            ax2.set_title('PSNR Score')
            ax2.set_ylabel('PSNR (dB)')
            ax2.grid(True, alpha=0.3)
            
            # SSIM subplot
            ax3.plot(frame_nums, ssim_scores, 'r-')
            ax3.set_title('SSIM Score')
            ax3.set_xlabel('Frame Number')
            ax3.set_ylabel('SSIM')
            ax3.grid(True, alpha=0.3)
            ax3.set_ylim(0, 1)
            
            plt.tight_layout()
            plt.savefig(combined_path, dpi=100)
            plt.close()
            chart_paths.append(combined_path)
            
            return chart_paths
            
        except Exception as e:
            logger.error(f"Error generating charts: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return chart_paths
    
    def _interpret_vmaf(self, score):
        """Interpret VMAF score"""
        if not isinstance(score, (int, float)):
            return "Unable to interpret"
            
        if score >= 90:
            return "Excellent quality (transparent)"
        elif score >= 80:
            return "Good quality (perceptible but not annoying)"
        elif score >= 70:
            return "Fair quality (slightly annoying)"
        elif score >= 60:
            return "Poor quality (annoying)"
        else:
            return "Bad quality (very annoying)"
    
    def _interpret_psnr(self, score):
        """Interpret PSNR score"""
        if not isinstance(score, (int, float)):
            return "Unable to interpret"
            
        if score >= 40:
            return "Excellent quality"
        elif score >= 30:
            return "Good quality"
        elif score >= 20:
            return "Acceptable quality"
        else:
            return "Poor quality"
    
    def _interpret_ssim(self, score):
        """Interpret SSIM score"""
        if not isinstance(score, (int, float)):
            return "Unable to interpret"
            
        if score >= 0.95:
            return "Excellent quality (imperceptible difference)"
        elif score >= 0.90:
            return "Good quality (perceptible but not annoying)"
        elif score >= 0.80:
            return "Fair quality (slightly annoying)"
        elif score >= 0.70:
            return "Poor quality (annoying)"
        else:
            return "Bad quality (very annoying)"

class ReportGeneratorThread(QThread):
    """Thread for report generation to prevent UI freezing"""
    report_progress = pyqtSignal(int)
    report_complete = pyqtSignal(str)
    report_error = pyqtSignal(str)
    
    def __init__(self, results, test_metadata=None, output_path=None):
        super().__init__()
        self.results = results
        self.test_metadata = test_metadata
        self.output_path = output_path
        self.generator = ReportGenerator()
        
        # Connect signals
        self.generator.report_progress.connect(self.report_progress)
        self.generator.report_complete.connect(self.report_complete)
        self.generator.report_error.connect(self.report_error)
    
    def run(self):
        """Run the report generation in a separate thread"""
        try:
            self.generator.generate_report(
                self.results,
                self.test_metadata,
                self.output_path
            )
        except Exception as e:
            logger.error(f"Error in report generation thread: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            self.report_error.emit(f"Thread error: {str(e)}")
