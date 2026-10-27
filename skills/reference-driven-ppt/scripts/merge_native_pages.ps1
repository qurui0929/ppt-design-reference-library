param([Parameter(Mandatory=$true)][string]$Manifest,[Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath $Output){throw 'Output already exists; use a new destination.'}
$items=@(Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json)
if($items.Count -eq 0){throw 'Manifest is empty.'}
$parent=Split-Path -Parent ([IO.Path]::GetFullPath($Output))
New-Item -ItemType Directory -Force $parent | Out-Null
$app=New-Object -ComObject PowerPoint.Application
$initialCount=$app.Presentations.Count
$deck=$null
try {
 $deck=$app.Presentations.Add(0)
 $first=$true
 foreach($entry in $items){
  $source=$null
  try {
   $source=$app.Presentations.Open($entry.path,-1,0,0)
   if($first){$deck.PageSetup.SlideWidth=$source.PageSetup.SlideWidth;$deck.PageSetup.SlideHeight=$source.PageSetup.SlideHeight;$first=$false}
   if([math]::Abs($deck.PageSetup.SlideWidth-$source.PageSetup.SlideWidth) -gt 0.1 -or [math]::Abs($deck.PageSetup.SlideHeight-$source.PageSetup.SlideHeight) -gt 0.1){throw 'Slide canvas differs.'}
   $start=if($null -ne $entry.start){[int]$entry.start}else{1}
   $end=if($null -ne $entry.end){[int]$entry.end}else{$source.Slides.Count}
   if($start -lt 1 -or $end -lt $start -or $end -gt $source.Slides.Count){throw 'Invalid slide range.'}
   $before=$deck.Slides.Count
   [void]$deck.Slides.InsertFromFile($entry.path,$before,$start,$end)
   for($index=$start;$index -le $end;$index++){
    $slide=$deck.Slides.Item($before+$index-$start+1)
    $slide.Design=$source.Slides.Item($index).Design
    $slide.ColorScheme=$source.Slides.Item($index).ColorScheme
    $slide.FollowMasterBackground=$source.Slides.Item($index).FollowMasterBackground
   }
  } finally {if($null -ne $source){$source.Close();[void][Runtime.InteropServices.Marshal]::ReleaseComObject($source)}}
 }
 $deck.SaveAs([IO.Path]::GetFullPath($Output),24)
 [pscustomobject]@{output=[IO.Path]::GetFullPath($Output);slides=$deck.Slides.Count;image_generation=$false}|ConvertTo-Json
} finally {
 if($null -ne $deck){$deck.Close();[void][Runtime.InteropServices.Marshal]::ReleaseComObject($deck)}
 if($initialCount -eq 0 -and $app.Presentations.Count -eq 0){$app.Quit()}
 [void][Runtime.InteropServices.Marshal]::ReleaseComObject($app)
}
