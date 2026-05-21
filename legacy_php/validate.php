  <?php  
    $loginFLG = false;
    session_start();
    if (isset($_SESSION['name']) and !empty($_SESSION['name'])) {
        if (time() - $_SESSION['last_activity'] > 1800){
            session_unset();
            session_destroy();
            $loginFLG = true;
            header('Location: timeout.php');
        }else{
            $loginFLG = true;
            $_SESSION['last_activity'] = time();
        }
    }
    if ($loginFLG == false){
        // Set the timezone to Pacific Standard Time
        $timezone = new DateTimeZone('America/Los_Angeles');
        // Create a new DateTime object with the current time
        $datetime1 = new DateTimeImmutable('now', $timezone);
        // Format the datetime as desired
        $currentDateTime = $datetime1->format('Y-m-d H:i:s');

        $title = isset($_GET['t']) ? $_GET['t'] : '';
        $dp = isset($_GET['dp']) ? $_GET['dp'] : '';
        switch ($dp){
            case "01":
                $department = "Sales";
                $dc = 2;
                break;
            case "02":
                $department = "PM";
                $dc = 3;
                break;
            case "03":
                $department = "Marketing";
                $dc = 4;
                break;
            case "10":
                $department = "Credit";
                $dc = 5;
                break;
            case "31":
                $department = "Production";
                $dc = 6;
                break;
            case "32":
                $department = "Planning";
                $dc = 7;
                break;
            case "55":
                $department = "Customer Service";
                $dc = 8;
                break;
            case "65":
                $department = "Purchasing";
                $dc = 9;
                break;
            case "85":
                $department = "Accounting";
                $dc = 10;
                break;
            case "86":
                $department = "Engineering";
                $dc = 11;
                break;
            case "88":
                $department = "MIS";
                $dc = 1;
                break;
            case "90":
                $department = "IT";
                $dc = 12;
                break;
            Default:
                $department = "Other";
                $dc = 13;
                break;
        }
        $datetime = isset($_GET['d']) ? $_GET['d'] : '';
        $encryptedString = isset($_GET['s']) ? $_GET['s'] : '';
        $authorization = isset($_GET['o']) ? $_GET['o'] : '5';
        $name = isset($_GET['ln']) ? $_GET['ln'] : 'AMAX';   
        $s_name = isset($_GET['n']) ? $_GET['n'] : 'HQ'; 
        $datetime2 = new DateTimeImmutable($datetime, $timezone);
        $string = $datetime2->format('Y-m-d H:i:s');
        $interval = $datetime2->diff($datetime1);
        $minutes = $interval->i + ($interval->h * 60) + ($interval->d * 24 * 60);
        if (empty($name) or empty($s_name) or empty($datetime) or empty($encryptedString) or empty($authorization) or $minutes > 1){
            header('Location: error.php');
        }
        $inputString = $datetime;
        $encryptionKey = $title;
        if ($encryptedString != encrypt($inputString, $encryptionKey)){
             header('Location: error.php');    
        }
        require('connection.php');
        $query = "SELECT * FROM employee WHERE name = '".$name."' and department= '".$dc."' and short_name = '".$s_name."'";
        $result = mysqli_query($conn, $query);
        if ($result && mysqli_num_rows($result) > 0) {
            $user = mysqli_fetch_assoc($result);
            if ($user == 2){
                header('Location: error.php'); 
            }
            $id = $user['id'];
            $authorization = $user['access_level'];
        }else{
            if ($title == "V.P." OR $title == "President"){
                $authorization = "1";
            }else{
                $authorization += 1;
            }
            $sql = "INSERT INTO employee (name, department, title, access_level, status, short_name)
              VALUES ('$name', '$dc', '$title', '$authorization', 1, '$s_name')";
              if ($conn->query($sql) === TRUE) {
                $id = $conn->insert_id;
              } else {
                echo "Connection error: " . $conn->error;
                return;
              }
        }
        // Close the database connection
        mysqli_close($conn);
        $_SESSION['name'] = $name;
        $_SESSION['id'] = $id;
        $_SESSION['short_name'] = $s_name;
        $_SESSION['department'] = $department;
        $_SESSION['department_code'] = $dc;
        $_SESSION['authorization'] = $authorization;
        $_SESSION['last_activity'] = time();
    }   
    if (!$loginFLG){
        echo "<p style='text-align:center'>Welcome ".ucwords(strtolower($_SESSION['name'])).". If this is not your name, please <a href='logout.php'>log out</a> immediately, go to SO and try again</p>";
    }else{
        echo "<a class='btn btn-sm btn-dark' type='button' href='logout.php'>Log out</a>";
    }
function encrypt($input, $key) {
    $encrypted = '';
    $output = '';
    $keyLength = strlen($key);
    $start = 97;
    for ($i = 0; $i < strlen($input); $i++) {
        $encrypted .= $input[$i] ^ $key[$i % $keyLength];
    }
    for ($i = 0; $i < strlen($encrypted); $i++) {
        $test = ord($encrypted[$i]);
        if (($test >= 65 and $test <= 90) or ($test >= 97 and $test <= 122)){
            $output .= $encrypted[$i];
        }else{
            $output .= chr($start);
            $start += 1;
        }
    }
    return $output;
}
?>