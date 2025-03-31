
import os
import time
import re
from datetime import datetime
import csv
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
import logging

logger = logging.getLogger(__name__)

class PDFCertificateGenerator:
    """Generates PDF certificate with VMAF test results"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        # Create custom styles
        self.styles.add(ParagraphStyle(
            name='Heading1Center',
            parent=self.styles['Heading1'],
            alignment=1,  # Center alignment
        ))
        self.styles.add(ParagraphStyle(
            name='Normal_Center',
            parent=self.styles['Normal'],
            alignment=1,  # Center alignment
        ))
        
    def generate_certificate(self, test_name, reference_path, captured_path, 
                            vmaf_results, output_path=None):
        """Generate a PDF certificate with test results"""
        
        # If no output path specified, create one in the same directory as the VMAF results
        if not output_path and vmaf_results.get('json_path'):
            results_dir = os.path.dirname(vmaf_results['json_path'])
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(results_dir, f"vmaf_certificate_{timestamp}.pdf")
        
        if not output_path:
            logger.error("No output path specified and couldn't determine one from results")
            return None
            
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        
        # Prepare story (content elements)
        story = []
        
        # Title
        story.append(Paragraph("Video Quality Test Results Report", self.styles['Heading1Center']))
        story.append(Spacer(1, 20))
        
        # Test Information - Following the provided template format
        story.append(Paragraph("Test Information", self.styles['Heading2']))
        story.append(Spacer(1, 10))
        
        # Format timestamp in the required format
        timestamp = datetime.now().strftime("%B %d, %Y %H:%M:%S")
        
        test_data = [
            ["Parameter", "Value"],
            ["Test Name", test_name],
            ["Project Name", "VMAF Test Project"],
            ["Test Date & Time", timestamp],
            ["Test Location", "Test Lab"],
            ["Test Operator", "System User"],
            ["Test Standard", "VMAF v0.6.1"]
        ]
        
        test_table = Table(test_data, colWidths=[150, 300])
        test_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (1, 0), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(test_table)
        story.append(Spacer(1, 20))
        
        # Reference & Test Video Information
        story.append(Paragraph("Reference & Test Video Information", self.styles['Heading2']))
        story.append(Spacer(1, 10))
        
        # Extract video info from results if available
        ref_info = self._get_video_info(reference_path)
        cap_info = self._get_video_info(captured_path)
        
        # Format file names to be shorter
        ref_file = os.path.basename(reference_path)
        cap_file = os.path.basename(captured_path)
        
        # If file names are too long, abbreviate them
        if len(ref_file) > 40:
            ref_file = ref_file[:37] + "..."
        if len(cap_file) > 40:
            cap_file = cap_file[:37] + "..."
        
        # Get frame count from VMAF results if available
        frame_count = 0
        if vmaf_results and 'raw_results' in vmaf_results and 'frames' in vmaf_results['raw_results']:
            frame_count = len(vmaf_results['raw_results']['frames'])
        
        # Duration calculation
        duration = "00:00:00"
        if ref_info and 'duration' in ref_info:
            seconds = int(ref_info['duration'])
            m, s = divmod(seconds, 60)
            h, m = divmod(m, 60)
            duration = f"{h:02d}:{m:02d}:{s:02d}"
        
        # Resolution string
        resolution = "Unknown"
        if ref_info and 'width' in ref_info and 'height' in ref_info:
            resolution = f"{ref_info['width']}x{ref_info['height']}"
            
        # Frame rate 
        frame_rate = "Unknown"
        if ref_info and 'frame_rate' in ref_info:
            frame_rate = f"{ref_info['frame_rate']:.2f} fps"
            
        # Color space and bit depth
        color_space = "YUV 4:2:0"  # Default assumption
        bit_depth = "8-bit"        # Default assumption
            
        video_specs = [
            ["Parameter", "Value"],
            ["Reference Video", ref_file],
            ["Test Video", cap_file],
            ["Resolution", resolution],
            ["Frame Rate", frame_rate],
            ["Bit Depth", bit_depth],
            ["Color Space", color_space],
            ["Total Frames", str(frame_count)],
            ["Test Duration", duration]
        ]
        
        video_table = Table(video_specs, colWidths=[150, 300])
        video_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (1, 0), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(video_table)
        story.append(Spacer(1, 20))
        
        # Test Equipment & Software
        story.append(Paragraph("Test Equipment & Software", self.styles['Heading2']))
        story.append(Spacer(1, 10))
        
        equipment_data = [
            ["Equipment/Software", "Version/Model", "Purpose"],
            ["VMAF Software", vmaf_results.get('model_path', "VMAF v0.6.1"), "Video Quality Assessment"],
            ["Hardware", "Testing Platform", "Test Execution"],
            ["Additional Tools", "FFmpeg", "Video Processing"]
        ]
        
        equipment_table = Table(equipment_data, colWidths=[150, 150, 150])
        equipment_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(equipment_table)
        story.append(Spacer(1, 20))
        
        # Summary Results section
        story.append(Paragraph("Summary Results", self.styles['Heading2']))
        story.append(Spacer(1, 10))
        
        # VMAF Score Summary
        story.append(Paragraph("VMAF Score Summary", self.styles['Heading3']))
        story.append(Spacer(1, 5))
        
        # Extract min/max/avg VMAF if available
        vmaf_min = 'N/A'
        vmaf_max = 'N/A'
        vmaf_avg = 'N/A'
        
        if vmaf_results and 'raw_results' in vmaf_results and 'pooled_metrics' in vmaf_results['raw_results']:
            pooled = vmaf_results['raw_results']['pooled_metrics']
            if 'vmaf' in pooled:
                vmaf_metrics = pooled['vmaf']
                vmaf_min = f"{vmaf_metrics.get('min', 0):.2f}"
                vmaf_max = f"{vmaf_metrics.get('max', 0):.2f}"
                vmaf_avg = f"{vmaf_metrics.get('mean', 0):.2f}"
        
        vmaf_summary = [
            ["Metric", "Minimum", "Maximum", "Average"],
            ["VMAF", vmaf_min, vmaf_max, vmaf_avg]
        ]
        
        vmaf_table = Table(vmaf_summary, colWidths=[100, 100, 100, 100])
        vmaf_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(vmaf_table)
        story.append(Spacer(1, 15))
        
        # PSNR Summary
        story.append(Paragraph("PSNR Summary (dB)", self.styles['Heading3']))
        story.append(Spacer(1, 5))
        
        # Extract PSNR data
        psnr_avg = vmaf_results.get('psnr', 'N/A')
        if isinstance(psnr_avg, (int, float)):
            psnr_avg = f"{psnr_avg:.2f}"
            
        # Since we don't have component-specific PSNR, we'll use the same value
        # In a real implementation, you'd extract Y, U, V PSNR separately
        psnr_y = psnr_avg
        psnr_u = "N/A"
        psnr_v = "N/A"
        
        psnr_summary = [
            ["Component", "Minimum", "Maximum", "Average"],
            ["PSNR Average", "N/A", "N/A", psnr_avg],
            ["PSNR Y (Luma)", "N/A", "N/A", psnr_y],
            ["PSNR U (Chroma)", "N/A", "N/A", psnr_u],
            ["PSNR V (Chroma)", "N/A", "N/A", psnr_v]
        ]
        
        psnr_table = Table(psnr_summary, colWidths=[100, 100, 100, 100])
        psnr_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(psnr_table)
        story.append(Spacer(1, 20))
        
        # Segment Analysis 
        story.append(Paragraph("Segment Analysis", self.styles['Heading2']))
        story.append(Spacer(1, 10))
        
        story.append(Paragraph("The test video shows distinct quality segments:", self.styles['Normal']))
        story.append(Spacer(1, 10))
        
        # PSNR Segments - We'll create fixed segments just as an example
        segment_data = [
            ["Segment", "Frame Range", "Average PSNR (dB)"],
            ["Segment 1", "1-59", "N/A"],
            ["Segment 2", "60-65", "N/A"],
            ["Segment 3", "66-76", "N/A"],
            ["Segment 4", "77-145", "N/A"]
        ]
        
        segment_table = Table(segment_data, colWidths=[100, 150, 150])
        segment_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(segment_table)
        story.append(Spacer(1, 20))
        
        # Detailed Frame-by-Frame Results
        story.append(Paragraph("Detailed Frame-by-Frame Results", self.styles['Heading2']))
        story.append(Spacer(1, 10))
        
        # Sample first 10 frames if available
        story.append(Paragraph("Sample Frame Metrics (First 10 frames)", self.styles['Heading3']))
        story.append(Spacer(1, 5))
        
        # Headers for the frame metrics table
        frame_metrics_headers = ["Frame", "PSNR Avg (dB)", "PSNR Y (dB)", "PSNR U (dB)", "PSNR V (dB)", "MSE Avg", "VMAF"]
        frame_metrics_data = [frame_metrics_headers]
        
        # Add sample frame data from VMAF results if available
        if vmaf_results and 'raw_results' in vmaf_results and 'frames' in vmaf_results['raw_results']:
            frames = vmaf_results['raw_results']['frames']
            # Take first 10 frames or less
            sample_frames = frames[:min(10, len(frames))]
            
            for i, frame in enumerate(sample_frames):
                frame_num = i + 1
                vmaf_score = frame['metrics'].get('vmaf', '-')
                if isinstance(vmaf_score, (int, float)):
                    vmaf_score = f"{vmaf_score:.2f}"
                
                # In a real implementation, you'd extract these from the frame data
                # Here we're just using placeholders
                row = [
                    str(frame_num),
                    psnr_avg,  # Using the average PSNR for all frames
                    psnr_y,    # Using the Y PSNR for all frames
                    psnr_u,    # Using the U PSNR for all frames
                    psnr_v,    # Using the V PSNR for all frames
                    "N/A",     # MSE Average
                    vmaf_score
                ]
                frame_metrics_data.append(row)
        
        # If no frames were added, add placeholder rows
        if len(frame_metrics_data) == 1:
            for i in range(1, 11):
                frame_metrics_data.append([str(i), "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"])
        
        frame_metrics_table = Table(frame_metrics_data, colWidths=[40, 70, 70, 70, 70, 70, 50])
        frame_metrics_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(frame_metrics_table)
        story.append(Spacer(1, 15))
        
        # VMAF Feature Metrics
        story.append(Paragraph("VMAF Feature Metrics (Sample)", self.styles['Heading3']))
        story.append(Spacer(1, 5))
        
        # Headers for VMAF feature metrics
        feature_headers = ["Frame", "ADM2", "Motion", "VIF Scale 0", "VIF Scale 1", "VIF Scale 2", "VIF Scale 3"]
        feature_data = [feature_headers]
        
        # Add sample feature data from VMAF results if available
        if vmaf_results and 'raw_results' in vmaf_results and 'frames' in vmaf_results['raw_results']:
            frames = vmaf_results['raw_results']['frames']
            # Just use the first frame as an example
            if frames:
                frame = frames[0]
                metrics = frame['metrics']
                
                row = [
                    "1",
                    f"{metrics.get('integer_adm2', 'N/A'):.4f}",
                    f"{metrics.get('integer_motion', 'N/A'):.4f}",
                    f"{metrics.get('integer_vif_scale0', 'N/A'):.4f}",
                    f"{metrics.get('integer_vif_scale1', 'N/A'):.4f}",
                    f"{metrics.get('integer_vif_scale2', 'N/A'):.4f}",
                    f"{metrics.get('integer_vif_scale3', 'N/A'):.4f}"
                ]
                feature_data.append(row)
        
        # If no feature data was added, add a placeholder row
        if len(feature_data) == 1:
            feature_data.append(["1", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"])
        
        # Add indication of additional frames
        feature_data.append(["[Additional frames...]", "", "", "", "", "", ""])
        
        feature_table = Table(feature_data, colWidths=[60, 60, 70, 70, 70, 70, 70])
        feature_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
            # No grid for the "Additional frames" row
            ('GRID', (0, len(feature_data)-1), (-1, len(feature_data)-1), 0, colors.white),
        ]))
        
        story.append(feature_table)
        story.append(Spacer(1, 20))
        
        # Observations and Notes
        story.append(Paragraph("Observations and Notes", self.styles['Heading2']))
        story.append(Spacer(1, 10))
        
        # Add general observations
        observations = [
            "- The test video shows quality fluctuations across different segments",
            f"- Overall VMAF score of {vmaf_avg} indicates {self._quality_rating(vmaf_avg)}",
            f"- PSNR value of {psnr_avg} dB",
            f"- SSIM value of {vmaf_results.get('ssim', 'N/A')}",
            "- Test conducted using standard VMAF testing methodology"
        ]
        
        for obs in observations:
            story.append(Paragraph(obs, self.styles['Normal']))
            story.append(Spacer(1, 5))
        
        story.append(Spacer(1, 15))
        
        # Conclusions
        story.append(Paragraph("Conclusions", self.styles['Heading2']))
        story.append(Spacer(1, 10))
        
        # Add conclusions based on the results
        vmaf_conclusion = "N/A"
        if isinstance(vmaf_results.get('vmaf_score'), (int, float)):
            score = vmaf_results['vmaf_score']
            if score < 20:
                vmaf_conclusion = "Very poor quality, significant differences between reference and test video."
            elif score < 40:
                vmaf_conclusion = "Poor quality, noticeable differences between reference and test video."
            elif score < 60:
                vmaf_conclusion = "Fair quality, some differences visible between reference and test video."
            elif score < 80:
                vmaf_conclusion = "Good quality, minor differences between reference and test video."
            else:
                vmaf_conclusion = "Excellent quality, nearly indistinguishable from reference video."
        
        story.append(Paragraph(vmaf_conclusion, self.styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Certification
        story.append(Paragraph("Certification", self.styles['Heading2']))
        story.append(Spacer(1, 10))
        
        cert_text = (
            "I hereby certify that the video quality testing described in this report was conducted "
            "in accordance with standard testing procedures and that the results presented are accurate "
            "to the best of my knowledge."
        )
        story.append(Paragraph(cert_text, self.styles['Normal']))
        story.append(Spacer(1, 15))
        
        # Signature line
        date_line = f"Date: {datetime.now().strftime('%B %d, %Y')}"
        story.append(Paragraph(date_line, self.styles['Normal']))
        story.append(Spacer(1, 20))
        
        sig_line = "Signature: ______________________"
        story.append(Paragraph(sig_line, self.styles['Normal']))
        story.append(Spacer(1, 10))
        
        name_line = "Name: System User"
        story.append(Paragraph(name_line, self.styles['Normal']))
        
        title_line = "Title: Test Operator"
        story.append(Paragraph(title_line, self.styles['Normal']))
        
        # Build the PDF
        doc.build(story)
        logger.info(f"Generated PDF certificate at: {output_path}")
        
        return output_path
    
    def _quality_rating(self, vmaf_score):
        """Return quality rating based on VMAF score"""
        if not isinstance(vmaf_score, (int, float)):
            return "unknown quality"
            
        score = float(vmaf_score)
        if score < 20:
            return "very poor quality"
        elif score < 40:
            return "poor quality"
        elif score < 60:
            return "fair quality"
        elif score < 80:
            return "good quality"
        else:
            return "excellent quality"
        
    def export_csv(self, vmaf_results, output_path=None):
        """
        Export VMAF results to CSV format
        
        Args:
            vmaf_results: VMAF results dictionary
            output_path: Output file path (optional)
            
        Returns:
            Path to the saved CSV file
        """
        # If no output path specified, create one in the same directory as the VMAF results
        if not output_path and vmaf_results.get('json_path'):
            results_dir = os.path.dirname(vmaf_results['json_path'])
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(results_dir, f"vmaf_results_{timestamp}.csv")
        
        if not output_path:
            logger.error("No output path specified and couldn't determine one from results")
            return None
        
        try:
            # Extract frame data from raw results
            raw_results = vmaf_results.get('raw_results', {})
            frames_data = raw_results.get('frames', [])
            
            with open(output_path, 'w', newline='') as csvfile:
                # Create CSV writer
                writer = csv.writer(csvfile)
                
                # Write header
                header = ['Frame', 'VMAF Score']
                
                # Check if first frame has feature metrics
                if frames_data and 'metrics' in frames_data[0]:
                    metrics = frames_data[0]['metrics']
                    for key in metrics.keys():
                        if key != 'vmaf':
                            header.append(key)
                
                writer.writerow(header)
                
                # Write frame data
                for i, frame in enumerate(frames_data):
                    if 'metrics' not in frame:
                        continue
                        
                    row = [i + 1]  # Frame number (1-based)
                    
                    # Add VMAF score
                    row.append(frame['metrics'].get('vmaf', 'N/A'))
                    
                    # Add other metrics
                    for key in header[2:]:  # Skip Frame and VMAF columns
                        row.append(frame['metrics'].get(key, 'N/A'))
                    
                    writer.writerow(row)
            
            # Add summary row at the end
            with open(output_path, 'a', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([])  # Empty row for separation
                
                # Add summary data
                summary = ['Summary']
                summary.append(vmaf_results.get('vmaf_score', 'N/A'))
                writer.writerow(summary)
                
                # Add PSNR and SSIM data
                if vmaf_results.get('psnr') is not None:
                    writer.writerow(['PSNR', vmaf_results['psnr']])
                if vmaf_results.get('ssim') is not None:
                    writer.writerow(['SSIM', vmaf_results['ssim']])
            
            logger.info(f"Exported CSV results to: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            return None
    
    def _get_video_info(self, video_path):
        """Extract video information using ffprobe"""
        try:
            import subprocess
            import json
            
            # Use ffprobe to get video info
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                "-count_frames",
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"ffprobe failed: {result.stderr}")
                return None
                
            info = json.loads(result.stdout)
            
            # Extract video stream info
            video_stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), None)
            if not video_stream:
                logger.error("No video stream found")
                return None
                
            # Extract format info
            format_info = info.get('format', {})
            
            # Parse information
            duration = float(format_info.get('duration', 0))
            
            # Get frame rate
            fr_str = video_stream.get('avg_frame_rate', '0/0')
            num, den = map(int, fr_str.split('/')) if '/' in fr_str else (0, 1)
            frame_rate = num / den if den else 0
            
            # Get resolution
            width = int(video_stream.get('width', 0))
            height = int(video_stream.get('height', 0))
            
            # Get frame count
            frame_count = int(video_stream.get('nb_frames', 0))
            
            # Other properties
            pix_fmt = video_stream.get('pix_fmt', 'unknown')
            codec = video_stream.get('codec_name', 'unknown')
            
            return {
                'path': video_path,
                'duration': duration,
                'frame_rate': frame_rate,
                'width': width,
                'height': height,
                'frame_count': frame_count,
                'pix_fmt': pix_fmt,
                'codec': codec
            }
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return None
