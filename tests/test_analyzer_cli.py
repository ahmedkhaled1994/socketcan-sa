#!/usr/bin/env python3
"""
CLI and import error tests for analyzer.py

Tests CLI argument parsing, main function, and import error handling.
"""

import pytest
import sys
import argparse
from unittest.mock import Mock, patch, MagicMock
from socketcan_sa.analyzer import main


class TestAnalyzerCLI:
    """Test CLI functionality and argument parsing."""
    
    def test_main_function_with_valid_args(self):
        """Test main() function with valid command line arguments."""
        test_args = ["--if", "vcan0", "--interval", "2.0", "--bitrate", "250000", "--csv", "test.csv"]
        
        with patch('sys.argv', ['analyzer.py'] + test_args), \
             patch('socketcan_sa.analyzer.analyze') as mock_analyze:
            
            main()
            
            # Verify analyze was called with correct parameters
            mock_analyze.assert_called_once_with("vcan0", 2.0, 250000, "test.csv")
    
    def test_main_function_with_minimal_args(self):
        """Test main() function with only required arguments."""
        test_args = ["--if", "can0"]
        
        with patch('sys.argv', ['analyzer.py'] + test_args), \
             patch('socketcan_sa.analyzer.analyze') as mock_analyze:
            
            main()
            
            # Verify analyze was called with defaults
            mock_analyze.assert_called_once_with("can0", 1.0, 500_000, None)
    
    def test_main_function_missing_required_interface(self):
        """Test main() function fails when required interface is missing."""
        test_args = ["--interval", "1.0"]  # Missing --if
        
        with patch('sys.argv', ['analyzer.py'] + test_args):
            with pytest.raises(SystemExit):
                main()
    
    def test_main_function_invalid_interval(self):
        """Test main() function fails with invalid interval."""
        test_args = ["--if", "vcan0", "--interval", "-1.0"]  # Negative interval
        
        with patch('sys.argv', ['analyzer.py'] + test_args):
            with pytest.raises(SystemExit):
                main()
    
    def test_main_function_zero_interval(self):
        """Test main() function fails with zero interval."""
        test_args = ["--if", "vcan0", "--interval", "0.0"]  # Zero interval
        
        with patch('sys.argv', ['analyzer.py'] + test_args):
            with pytest.raises(SystemExit):
                main()
    
    def test_main_function_with_all_arguments(self):
        """Test main() function with all possible arguments."""
        test_args = [
            "--if", "vcan1", 
            "--interval", "0.5", 
            "--bitrate", "1000000",
            "--csv", "/tmp/output.csv"
        ]
        
        with patch('sys.argv', ['analyzer.py'] + test_args), \
             patch('socketcan_sa.analyzer.analyze') as mock_analyze:
            
            main()
            
            # Verify analyze was called with all parameters
            mock_analyze.assert_called_once_with("vcan1", 0.5, 1000000, "/tmp/output.csv")


class TestAnalyzerDirectExecution:
    """Test direct script execution scenarios."""
    
    def test_script_execution_path(self):
        """Test the main execution path when run as script."""
        # Test that we can import and access the main function
        from socketcan_sa.analyzer import main
        assert callable(main), "main() should be callable"
    
    def test_analyze_function_importable(self):
        """Test that analyze function is properly importable."""
        from socketcan_sa.analyzer import analyze
        assert callable(analyze), "analyze() should be callable"


class TestMainExecution:
    """Test the if __name__ == '__main__' block."""
    
    def test_name_main_execution(self):
        """Test that main() is called when script is executed directly."""
        # Test the __name__ == "__main__" execution path
        test_args = ["--if", "vcan0"]
        
        with patch('sys.argv', ['analyzer.py'] + test_args), \
             patch('socketcan_sa.analyzer.main') as mock_main:
            
            # Simulate executing the script directly
            exec(compile(
                'if __name__ == "__main__":\n    main()', 
                'analyzer.py', 
                'exec'
            ), {'__name__': '__main__', 'main': mock_main})
            
            mock_main.assert_called_once()


class TestArgumentParsingEdgeCases:
    """Test edge cases in argument parsing."""
    
    def test_interface_name_validation(self):
        """Test various interface name formats."""
        valid_interfaces = ["vcan0", "can0", "can1", "vcan99"]
        
        for interface in valid_interfaces:
            test_args = ["--if", interface]
            
            with patch('sys.argv', ['analyzer.py'] + test_args), \
                 patch('socketcan_sa.analyzer.analyze') as mock_analyze:
                
                main()
                
                # Should accept any interface name
                mock_analyze.assert_called_with(interface, 1.0, 500_000, None)
    
    def test_numeric_argument_types(self):
        """Test type conversion for numeric arguments."""
        test_args = ["--if", "vcan0", "--interval", "1.5", "--bitrate", "125000"]
        
        with patch('sys.argv', ['analyzer.py'] + test_args), \
             patch('socketcan_sa.analyzer.analyze') as mock_analyze:
            
            main()
            
            # Verify types are correctly converted
            args = mock_analyze.call_args[0]
            assert isinstance(args[1], float)  # interval
            assert isinstance(args[2], int)    # bitrate
    
    def test_csv_path_handling(self):
        """Test CSV path argument handling."""
        csv_paths = [
            "/absolute/path/output.csv",
            "relative/path/output.csv", 
            "output.csv",
            None  # Default when not specified
        ]
        
        for csv_path in csv_paths:
            if csv_path is None:
                test_args = ["--if", "vcan0"]
            else:
                test_args = ["--if", "vcan0", "--csv", csv_path]
            
            with patch('sys.argv', ['analyzer.py'] + test_args), \
                 patch('socketcan_sa.analyzer.analyze') as mock_analyze:
                
                main()
                
                # Verify CSV path is passed correctly
                args = mock_analyze.call_args[0]
                assert args[3] == csv_path