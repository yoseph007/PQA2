
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
        
        # Test Information
        story.append(Paragraph("Test Information", self.styles['Heading2']))
        story.append(Spacer(1, 10))
        
        # Test metadata
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        test_data = [
            ["Test Name:", test_name],
            ["Date/Time:", timestamp],
            ["Project Name:", "VMAF Test Project"],
            ["Test Location:", "Lab Environment"],
            ["Test Operator:", "System User"],
        ]
        
        test_table = Table(test_data, colWidths=[120, 300])
        test_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(test_table)
        story.append(Spacer(1, 20))
        
        # Extract video info from results if available
        ref_info = self._get_video_info(reference_path)
        cap_info = self._get_video_info(captured_path)
        
        # Video Specifications
        story.append(Paragraph("Video Specifications", self.styles['Heading2']))
        story.append(Spacer(1, 10))
        
        # Prepare video info
        video_specs = [
            ["", "Reference Video", "Captured Video"],
            ["Path:", os.path.basename(reference_path), os.path.basename(captured_path)],
        ]
        
        # Add resolution, frame rate, duration if available
        if ref_info and cap_info:
            video_specs.extend([
                ["Resolution:", f"{ref_info['width']}x{ref_info['height']}", f"{cap_info['width']}x{cap_info['height']}"],
                ["Frame Rate:", f"{ref_info['frame_rate']:.2f} fps", f"{cap_info['frame_rate']:.2f} fps"],
                ["Duration:", f"{ref_info['duration']:.2f}s", f"{cap_info['duration']:.2f}s"],
                ["Total Frames:", f"{ref_info['frame_count']}", f"{cap_info['frame_count']}"],
            ])
        
        video_table = Table(video_specs, colWidths=[120, 180, 180])
        video_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('BACKGROUND', (0, 1), (0, -1), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(video_table)
        story.append(Spacer(1, 20))
        
        # VMAF Results
        story.append(Paragraph("Video Quality Analysis Results", self.styles['Heading2']))
        story.append(Spacer(1, 10))
        
        # Extract scores from results
        vmaf_score = vmaf_results.get('vmaf_score', 'N/A')
        if isinstance(vmaf_score, (int, float)):
            vmaf_score = f"{vmaf_score:.2f}"
            
        psnr = vmaf_results.get('psnr', 'N/A')
        if isinstance(psnr, (int, float)):
            psnr = f"{psnr:.2f} dB"
            
        ssim = vmaf_results.get('ssim', 'N/A')
        if isinstance(ssim, (int, float)):
            ssim = f"{ssim:.4f}"
        
        # Extract min/max VMAF if available in raw results
        vmaf_min = 'N/A'
        vmaf_max = 'N/A'
        
        raw_results = vmaf_results.get('raw_results', {})
        if raw_results and 'frames' in raw_results:
            try:
                vmaf_scores = [frame['metrics'].get('vmaf', 0) for frame in raw_results['frames']]
                if vmaf_scores:
                    vmaf_min = f"{min(vmaf_scores):.2f}"
                    vmaf_max = f"{max(vmaf_scores):.2f}"
            except (KeyError, TypeError):
                pass
        
        vmaf_data = [
            ["VMAF Model:", vmaf_results.get('model_path', 'Unknown')],
            ["VMAF Score:", vmaf_score],
            ["VMAF Min:", vmaf_min],
            ["VMAF Max:", vmaf_max],
            ["PSNR:", psnr],
            ["SSIM:", ssim],
        ]
        
        vmaf_table = Table(vmaf_data, colWidths=[120, 300])
        vmaf_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(vmaf_table)
        story.append(Spacer(1, 20))
        
        # Technical Notes
        story.append(Paragraph("Technical Notes", self.styles['Heading2']))
        story.append(Spacer(1, 10))
        
        # Get result file paths
        json_path = vmaf_results.get('json_path', 'N/A')
        csv_path = vmaf_results.get('csv_path', 'N/A')
        psnr_log = vmaf_results.get('psnr_log', 'N/A')
        ssim_log = vmaf_results.get('ssim_log', 'N/A')
        
        if isinstance(json_path, str):
            json_path = os.path.basename(json_path)
        if isinstance(csv_path, str):
            csv_path = os.path.basename(csv_path)
        if isinstance(psnr_log, str):
            psnr_log = os.path.basename(psnr_log)
        if isinstance(ssim_log, str):
            ssim_log = os.path.basename(ssim_log)
        
        notes_data = [
            ["Output Files:", f"VMAF JSON: {json_path}"],
            ["", f"VMAF CSV: {csv_path}"],
            ["", f"PSNR Log: {psnr_log}"],
            ["", f"SSIM Log: {ssim_log}"],
        ]
        
        notes_table = Table(notes_data, colWidths=[120, 300])
        notes_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (0, 0), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('SPAN', (0, 0), (0, 3)),  # Span the first column
        ]))
        
        story.append(notes_table)
        story.append(Spacer(1, 30))
        
        # Certificate footer
        story.append(Paragraph(
            f"Generated by VMAF Test App on {timestamp}",
            self.styles['Normal_Center']
        ))
        
        # Build the PDF
        doc.build(story)
        logger.info(f"Generated PDF certificate at: {output_path}")
        
        return output_path
        
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
                    writer.writerow(['PSNR (dB)', vmaf_results['psnr']])
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
