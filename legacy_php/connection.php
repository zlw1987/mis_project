<?php

  // Database connection details
    $host = 'localhost';
    $username = 'MIS';
    $password = 'MISUSER123!';
    $database = 'mis_project';

  // Create a database connection
  $conn = new mysqli($host, $username, $password, $database);
    // Check the connection
  if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
   }
?>