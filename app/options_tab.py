# Add frame sampling settings for bookend alignment
        frame_sampling_group = QGroupBox("Bookend Alignment Settings")
        frame_sampling_layout = QVBoxLayout()

        # Frame sampling rate slider (1-30)
        frame_sampling_label = QLabel("Frame Sampling Rate:")
        frame_sampling_layout.addWidget(frame_sampling_label)

        self.frame_sampling_slider = QSlider(Qt.Horizontal)
        self.frame_sampling_slider.setMinimum(1)
        self.frame_sampling_slider.setMaximum(30)
        self.frame_sampling_slider.setValue(5)  # Default value
        self.frame_sampling_slider.setTickPosition(QSlider.TicksBelow)
        self.frame_sampling_slider.setTickInterval(5)

        frame_sampling_layout.addWidget(self.frame_sampling_slider)

        # Display current value
        self.frame_sampling_value_label = QLabel("5 (checks every 5th frame)")
        frame_sampling_layout.addWidget(self.frame_sampling_value_label)

        # Connect slider value changed signal
        self.frame_sampling_slider.valueChanged.connect(self._update_frame_sampling_label)

        # Add hint about performance
        frame_sampling_hint = QLabel("Hint: Lower values check more frames (higher accuracy, slower)")
        frame_sampling_hint.setStyleSheet("color: gray; font-style: italic;")
        frame_sampling_layout.addWidget(frame_sampling_hint)

        frame_sampling_group.setLayout(frame_sampling_layout)
        main_layout.addWidget(frame_sampling_group)

        # VMAF Models section
        vmaf_group = QGroupBox("VMAF Processing")
        vmaf_layout = QVBoxLayout()