<?php  
    session_start();
    session_unset();
    session_destroy();
    echo "You have successfully logged out! Please close this page.";
?>
 